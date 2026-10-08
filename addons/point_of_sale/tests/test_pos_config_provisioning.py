import logging

from odoo import Command
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.point_of_sale.tests.common import TestPoSCommon

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestPosConfigProvisioning(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.config = cls.basic_config

    def test_cash_reference_must_identify_an_active_cash_method(self):
        Config = self.env["pos.config"]
        archived = self.cash_pm1.copy({"active": False})
        for record in (self.bank_pm1, archived, self.env.company):
            with self.subTest(model=record._name, record=record.id):
                reference = Config._get_suffixed_ref_name(
                    "point_of_sale.provisioning_invalid_cash"
                )
                self.env["ir.model.data"]._update_xmlids(
                    [
                        {"xml_id": reference, "record": record, "noupdate": True},
                    ]
                )
                _logger.debug(
                    "Cash reference validation model=%s id=%s", record._name, record.id
                )
                with self.assertRaises(UserError):
                    Config._create_journal_and_payment_methods(
                        cash_ref="point_of_sale.provisioning_invalid_cash"
                    )

    def test_cash_creation_rejects_non_cash_journal(self):
        _logger.debug("Rejecting bank journal override in cash provisioning")
        with self.assertRaises(UserError):
            self.env["pos.config"]._create_cash_payment_method({"type": "bank"})

    def test_cash_creation_rejects_foreign_company_override(self):
        company = self.env["res.company"].create({"name": "Foreign cash override"})
        _logger.debug("Rejecting cash company override %s", company.id)
        with self.assertRaises(UserError):
            self.env["pos.config"]._create_cash_payment_method(
                {"company_id": company.id}
            )

    def test_provisioning_does_not_reuse_anonymous_customer_accounts(self):
        self.env["pos.payment.method"].search(
            [
                ("company_id", "=", self.env.company.id),
                ("journal_id", "=", False),
            ]
        ).write({"active": False})
        anonymous = self.env["pos.payment.method"].create(
            {
                "name": "Anonymous receivable",
                "company_id": self.env.company.id,
                "split_transactions": False,
            }
        )
        _journal, ids = self.env["pos.config"]._create_journal_and_payment_methods()
        methods = self.env["pos.payment.method"].browse(ids)
        _logger.debug(
            "Provisioned customer accounts=%s anonymous=%s",
            methods.filtered(lambda method: not method.journal_id).ids,
            anonymous.id,
        )
        self.assertNotIn(anonymous, methods)
        self.assertTrue(methods.filtered(lambda method: not method.journal_id))
        self.assertTrue(
            all(
                method.split_transactions for method in methods if not method.journal_id
            )
        )

    def test_provisioning_excludes_archived_methods_with_active_test_disabled(self):
        archived = self.bank_pm1.copy({"name": "Archived card", "active": False})
        _journal, ids = (
            self.env["pos.config"]
            .with_context(active_test=False)
            ._create_journal_and_payment_methods()
        )
        methods = self.env["pos.payment.method"].browse(ids)
        _logger.debug("Provisioned methods=%s archived=%s", ids, archived.id)
        self.assertNotIn(archived, methods)
        self.assertTrue(all(method.active for method in methods))

    def test_branch_payment_methods_belong_to_the_branch(self):
        branch = self.env["res.company"].create(
            {
                "name": "POS branch",
                "parent_id": self.config.company_id.id,
            }
        )

        branch_config = self.config.with_context(
            allowed_company_ids=[branch.id, self.config.company_id.id]
        )
        self.assertIn(self.bank_pm1, branch_config.env["pos.payment.method"].search([]))
        _journal, method_ids = branch_config._create_journal_and_payment_methods()

        methods = self.env["pos.payment.method"].browse(method_ids)
        self.assertEqual(set(methods.mapped("type")), {"cash", "bank", "pay_later"})
        self.assertEqual(methods.company_id, branch)

    def test_a_config_can_be_created_for_a_company_other_than_the_active_one(self):
        company = self.env["res.company"].create({"name": "Audit Second Co"})
        self.env["account.chart.template"].try_loading(
            "generic_coa", company=company, install_demo=False
        )
        self.env.invalidate_all()
        config = self.env["pos.config"].create(
            {"name": "other-company-shop", "company_id": company.id}
        )
        self.assertEqual(config.company_id, company)
        self.assertEqual(config.picking_type_id.company_id, company)
        self.assertTrue(config.payment_method_ids)
        for method in config.payment_method_ids:
            self.assertEqual(method.company_id, company)

    def test_each_company_in_a_batch_gets_its_own_warehouse(self):
        company = self.env["res.company"].create({"name": "Audit Third Co"})
        self.env["account.chart.template"].try_loading(
            "generic_coa", company=company, install_demo=False
        )
        self.env["stock.warehouse"].search([("company_id", "=", company.id)]).unlink()
        self.env.invalidate_all()
        self.env["pos.config"].with_context(
            allowed_company_ids=[self.env.company.id, company.id]
        ).create([{"name": "Alpha"}, {"name": "Bravo", "company_id": company.id}])
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", company.id)]
        )
        self.assertTrue(warehouse, "the second company got no warehouse")
        self.assertEqual(warehouse.code.upper(), "BRA")

    def test_the_removed_helpers_stay_removed(self):
        for gone in (
            "_get_or_create_journal_id",
            "_get_or_create_payment_method_id",
            "_link_same_non_cash_payment_methods",
            "_check_groups_implied",
            "execute",
        ):
            self.assertFalse(
                hasattr(self.env["pos.config"], gone),
                f"{gone} was removed as dead code; reintroducing it needs a caller",
            )

    def test_cash_journal_preserves_explicit_default_account(self):
        Account = self.env["account.account"]
        fallback = Account.create(
            {
                "name": "Cash",
                "code": "CHCASH1",
                "account_type": "asset_cash",
                "company_ids": [Command.set(self.env.company.root_id.ids)],
            }
        )
        explicit = fallback.copy({"name": "Dedicated POS cash", "code": "CHCASH2"})
        method = self.env["pos.config"]._create_cash_payment_method(
            {"default_account_id": explicit.id}
        )
        _logger.debug(
            "Cash provisioning explicit=%s selected=%s",
            explicit.id,
            method.journal_id.default_account_id.id,
        )
        self.assertEqual(method.journal_id.default_account_id, explicit)

    def test_cash_reference_cannot_reintroduce_a_parent_payment_method(self):
        branch = self.env["res.company"].create(
            {"name": "Cash reference branch", "parent_id": self.config.company_id.id}
        )
        ref = "point_of_sale.challenge_parent_cash"
        self.env["ir.model.data"]._update_xmlids(
            [{"xml_id": ref, "record": self.cash_pm1, "noupdate": True}]
        )
        config = self.config.with_context(
            allowed_company_ids=[branch.id, self.config.company_id.id]
        )

        _journal, method_ids = config._create_journal_and_payment_methods(cash_ref=ref)

        self.assertEqual(
            self.env["pos.payment.method"].browse(method_ids).company_id, branch
        )
        self.assertEqual(self.env.ref(ref), self.cash_pm1)
        local_ref = config._get_suffixed_ref_name(ref)
        self.assertEqual(self.env.ref(local_ref).company_id, branch)
        _journal, repeated_ids = config._create_journal_and_payment_methods(
            cash_ref=ref
        )
        self.assertEqual(set(repeated_ids), set(method_ids))

    def test_misowned_company_cash_reference_is_rejected(self):
        branch = self.env["res.company"].create(
            {
                "name": "Misowned reference branch",
                "parent_id": self.config.company_id.id,
            }
        )
        config = self.config.with_context(
            allowed_company_ids=[branch.id, self.config.company_id.id]
        )
        ref = "point_of_sale.challenge_misowned_cash"
        self.env["ir.model.data"]._update_xmlids(
            [
                {
                    "xml_id": config._get_suffixed_ref_name(ref),
                    "record": self.cash_pm1,
                    "noupdate": True,
                }
            ]
        )

        with self.assertRaisesRegex(UserError, "must belong to the current company"):
            config._create_journal_and_payment_methods(cash_ref=ref)

    def test_branch_can_open_a_session_with_provisioned_methods(self):
        parent = self.env["res.company"].create(
            {"name": "Provisioning parent", "country_id": self.env.ref("base.us").id}
        )
        self.env["account.chart.template"].try_loading(
            "generic_coa", company=parent, install_demo=False
        )
        self.assertEqual(parent.account_config_id.chart_template, "generic_coa")
        self.env["pos.config"].with_company(
            parent
        )._create_journal_and_payment_methods()
        branch = self.env["res.company"].create(
            {
                "name": "End-to-end branch",
                "parent_id": parent.id,
                "country_id": parent.country_id.id,
            }
        )
        Config = self.env["pos.config"].with_context(
            allowed_company_ids=[branch.id, parent.id]
        )
        journal, method_ids = Config._create_journal_and_payment_methods()
        config = Config.create(
            {
                "name": "Branch shop",
                "company_id": branch.id,
                "journal_id": journal.id,
                "payment_method_ids": [Command.set(method_ids)],
            }
        )

        self.assertTrue(config.company_has_template)
        action = config.open_ui()

        self.assertEqual(config.current_session_id.company_id, branch)
        self.assertEqual(config.payment_method_ids.company_id, branch)
        self.assertIn(f"/pos/ui/{config.id}", action["url"])
