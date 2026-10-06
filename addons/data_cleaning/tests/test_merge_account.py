from odoo import Command
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged, users

from odoo.addons.data_cleaning.models.res_partner import ResPartner


@tagged("post_install", "-at_install")
class TestMerge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "account.account" not in cls.env:
            cls.skipTest(cls, "`account` module not installed")

        cls.customer_invoice_journal = cls.env["account.journal"].search(
            [("company_id", "=", cls.env.company.id), ("name", "=", "Sales")]
        )
        cls.account_sale_a = cls.env["account.account"].create(
            {
                "code": "40001",
                "name": "Account Sale A",
                "account_type": "asset_receivable",
                "reconcile": True,
            }
        )
        cls.account_sale_b = cls.env["account.account"].create(
            {
                "code": "40002",
                "name": "Account Sale B",
                "account_type": "asset_receivable",
                "reconcile": True,
            }
        )
        cls.partner_a = cls.env["res.partner"].create({"name": "Partner A"})
        cls.partner_b = cls.env["res.partner"].create({"name": "Partner B"})

    def _enable_merge(self, model_name):
        self.res_model_id = self.env["ir.model"].search([("model", "=", model_name)])
        self.res_model_id.action_merge_contextual_enable()
        self.model_id = self.env["data_merge.model"].create(
            {
                "name": model_name,
                "res_model_id": self.res_model_id.id,
            }
        )

    def test_merge_account(self):
        """Test that we cannot merge accounts."""
        self._enable_merge("account.account")

        data_merge_group = self.env["data_merge.group"].create(
            {
                "model_id": self.model_id.id,
                "res_model_id": self.res_model_id.id,
                "record_ids": [
                    (
                        0,
                        0,
                        {
                            "res_id": self.account_sale_a.id,
                            "is_master": True,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "res_id": self.account_sale_b.id,
                        },
                    ),
                ],
            }
        )

        # the {group_id: record_ids} dict is what the list view sends to merge_multiple_records
        group_records = {str(data_merge_group.id): data_merge_group.record_ids.ids}
        with self.assertRaises(UserError, msg="You cannot merge accounts."):
            self.env["data_merge.group"].merge_multiple_records(group_records)

    @users("admin")
    def test_merge_partner_in_hashed_entries(self):
        """Test that we cannot merge partners used in hashed entries."""
        self.env.user.write(
            {"group_ids": [(4, self.env.ref("account.group_account_user").id)]}
        )
        self._enable_merge("res.partner")
        move_1 = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2023-07-21",
                "partner_id": self.partner_b.id,
                "invoice_line_ids": [
                    Command.create({"name": "test line", "price_unit": 1000})
                ],
            }
        )
        move_1.action_post()

        self.customer_invoice_journal.restrict_mode_hash_table = True

        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2023-07-22",
                "partner_id": self.partner_b.id,
                "invoice_line_ids": [
                    Command.create({"name": "test line", "price_unit": 1000})
                ],
            }
        )
        move.action_post()

        # The integrity check should work
        integrity_check = move.company_id._check_hash_integrity()["results"]
        integrity_check = next(
            filter(
                lambda j: move.sequence_prefix in j.get("journal_name"), integrity_check
            )
        )
        self.assertRegex(integrity_check["msg_cover"], "Entries are correctly hashed")

        data_merge_group = self.env["data_merge.group"].create(
            {
                "model_id": self.model_id.id,
                "res_model_id": self.res_model_id.id,
                "record_ids": [
                    (
                        0,
                        0,
                        {
                            "res_id": self.partner_a.id,
                            "is_master": True,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "res_id": self.partner_b.id,
                        },
                    ),
                ],
            }
        )

        # the {group_id: record_ids} dict is what the list view sends to merge_multiple_records
        group_records = {str(data_merge_group.id): data_merge_group.record_ids.ids}
        with self.assertRaises(
            UserError,
            msg="Records that are used as fields in hashed entries cannot be merged.",
        ):
            self.env["data_merge.group"].merge_multiple_records(group_records)

    def _hashed_invoice(self, partner):
        self.customer_invoice_journal.restrict_mode_hash_table = True
        move = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "invoice_date": "2023-07-22",
                "partner_id": partner.id,
                "invoice_line_ids": [
                    Command.create({"name": "test line", "price_unit": 1000})
                ],
            }
        )
        move.action_post()
        self.assertTrue(move.inalterable_hash)
        return move

    def test_merging_a_partner_of_hashed_entries_is_refused_on_top_of_account(self):
        self._hashed_invoice(self.partner_b)

        # data_cleaning's own definition, as it runs when its class sits above
        # account's in the MRO (data_cleaning installed into a database that
        # already holds account)
        with self.assertRaisesRegex(UserError, "used in hashed entries"):
            ResPartner._merge_method(
                self.env["res.partner"], self.partner_a, self.partner_b
            )
        self.assertTrue(self.partner_b.exists())

    def test_merging_partners_without_hashed_entries(self):
        self._hashed_invoice(self.partner_a)
        self._enable_merge("res.partner")
        data_merge_group = self.env["data_merge.group"].create(
            {
                "model_id": self.model_id.id,
                "res_model_id": self.res_model_id.id,
                "record_ids": [
                    Command.create({"res_id": self.partner_a.id, "is_master": True}),
                    Command.create({"res_id": self.partner_b.id}),
                ],
            }
        )

        self.env["data_merge.group"].merge_multiple_records(
            {str(data_merge_group.id): data_merge_group.record_ids.ids}
        )

        self.assertTrue(self.partner_a.exists())
        self.assertFalse(self.partner_b.exists())
