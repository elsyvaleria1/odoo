from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.base.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestAssetLogTyping(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("asset_ledger.group_asset_manager")
        cls.company = cls.company_data["company"]
        cls.fuel_account = cls.company_data["default_account_expense"]
        cls.fuel_account.asset_log_type = "fuel"

        product = cls.env["product.product"].sudo()
        cls.machine_product = product.create(
            {
                "name": "Typing probe machine",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("base.kind_machinery").id,
            }
        )
        cls.service_product = product.create(
            {
                "name": "Typing probe service",
                "type": "service",
                "categ_id": cls.env.ref(
                    "asset_ledger.product_category_maintenance_and_repairs"
                ).id,
            }
        )
        cls.machine = cls.env["product.trace"].create(
            {
                "name": "TYPING-MC-1",
                "product_id": cls.machine_product.id,
                "company_id": cls.company.id,
            }
        )
        cls.vendor = cls.env["res.partner"].create({"name": "Typing probe vendor"})

    def _bill_line(self, product=None):
        move = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.vendor.id,
                "invoice_date": "2026-01-15",
                "company_id": self.company.id,
                "journal_id": self.company_data["default_journal_purchase"].id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "name": "probe",
                            "product_id": product.id if product else False,
                            "account_id": self.fuel_account.id,
                            "asset_id": self.machine.asset_id.id,
                            "quantity": 1.0,
                            "price_unit": 100.0,
                            "tax_ids": [(5, 0, 0)],
                        },
                    )
                ],
            }
        )
        return move.invoice_line_ids[:1]

    def test_a_line_with_a_product_is_typed_by_its_category(self):
        line = self._bill_line(self.service_product)
        self.assertEqual(line.asset_log_ids.log_type, "service")

    def test_a_line_with_no_product_is_typed_by_its_account(self):
        line = self._bill_line()
        self.assertFalse(line.product_id)
        self.assertEqual(
            line.asset_log_ids.log_type,
            "fuel",
            "an account-only bill line must still land in a bucket",
        )

    def test_a_product_whose_category_types_nothing_falls_back_to_the_account(self):
        untyped = (
            self.env["product.category"]
            .sudo()
            .create({"name": "Typing probe untyped category"})
        )
        product = (
            self.env["product.product"]
            .sudo()
            .create(
                {
                    "name": "Typing probe untyped service",
                    "type": "service",
                    "categ_id": untyped.id,
                }
            )
        )
        line = self._bill_line(product)

        self.assertTrue(line.product_id)
        self.assertFalse(line.product_id.categ_id.log_type)
        self.assertEqual(
            line.asset_log_ids.log_type,
            "fuel",
            "the account is the fallback whenever the category types nothing, "
            "not only when the line carries no product",
        )

    def test_the_product_category_outranks_the_account(self):
        line = self._bill_line(self.service_product)
        self.assertEqual(self.fuel_account.asset_log_type, "fuel")
        self.assertEqual(line.asset_log_ids.log_type, "service")

    def test_an_untyped_account_leaves_the_log_untyped(self):
        self.fuel_account.asset_log_type = False
        line = self._bill_line()
        self.assertFalse(line.asset_log_ids.log_type)

    def test_typing_the_account_types_what_it_already_booked(self):
        self.fuel_account.asset_log_type = False
        line = self._bill_line()
        self.assertFalse(line.asset_log_ids.log_type)

        self.fuel_account.asset_log_type = "fuel"

        self.assertEqual(
            line.asset_log_ids.log_type,
            "fuel",
            "the log re-derives its type from its line, so typing the account "
            "is enough on its own",
        )

    def test_the_field_is_gated_for_a_non_asset_manager(self):
        accountant = new_test_user(
            self.env,
            login="apa_accountant",
            groups="base.group_user,account.group_account_manager",
            company_id=self.company.id,
        )
        self.assertFalse(accountant.has_group("asset_ledger.group_asset_manager"))

        gated = self.fuel_account.with_user(accountant)
        self.assertRaises(AccessError, getattr, gated, "asset_log_type")

    def test_a_non_asset_manager_can_still_bill_an_asset(self):
        biller = new_test_user(
            self.env,
            login="apa_biller",
            groups="base.group_user,account.group_account_user,"
            "asset_ledger.group_asset_user,asset_ledger.group_enable_machinery_assets",
            company_id=self.company.id,
        )

        move = (
            self.env["account.move"]
            .with_user(biller)
            .create(
                {
                    "move_type": "in_invoice",
                    "partner_id": self.vendor.id,
                    "invoice_date": "2026-01-15",
                    "company_id": self.company.id,
                    "journal_id": self.company_data["default_journal_purchase"].id,
                    "invoice_line_ids": [
                        (
                            0,
                            0,
                            {
                                "name": "gated typing probe",
                                "account_id": self.fuel_account.id,
                                "asset_id": self.machine.asset_id.id,
                                "quantity": 1.0,
                                "price_unit": 100.0,
                                "tax_ids": [(5, 0, 0)],
                            },
                        )
                    ],
                }
            )
        )
        move.flush_recordset()

        self.assertEqual(
            move.invoice_line_ids.asset_log_ids.log_type,
            "fuel",
            "typing a log is a side effect of booking the bill, so the gate on "
            "the field must not reach the accountant posting it",
        )
