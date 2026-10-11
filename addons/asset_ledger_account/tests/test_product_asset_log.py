from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestProductAssetLog(AccountTestInvoicingCommon):
    chart_template = "generic_coa"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids |= cls.env.ref("asset_ledger.group_asset_manager")

        cls.test_company = cls.company_data["company"]
        cls.expense_account = cls.company_data["default_account_expense"]
        cls.purchase_journal = cls.company_data["default_journal_purchase"] or (
            cls.env["account.journal"].create(
                {
                    "name": "Test Purchase",
                    "type": "purchase",
                    "code": "TBILL",
                    "company_id": cls.test_company.id,
                }
            )
        )
        assert (
            cls.purchase_journal.id
            and cls.purchase_journal.company_id == cls.test_company
            and cls.purchase_journal.type == "purchase"
        ), (
            f"purchase_journal invalid: id={cls.purchase_journal.id} "
            f"company={cls.purchase_journal.company_id.name} "
            f"type={cls.purchase_journal.type}"
        )

        cls.AccountMove = cls.env["account.move"]
        cls.AccountMoveLine = cls.env["account.move.line"]
        cls.ProductTrace = cls.env["product.trace"]
        cls.ProductAssetLog = cls.env["resource.log"]
        # sudo: these are fixtures. marin gates product.template.standard_price
        # with write_groups, so building them as the suite's deliberately
        # under-privileged accounting user dies in setUpClass wherever it is
        # installed. Access is exercised by the tests, not by the setup.
        cls.ProductProduct = cls.env["product.product"].sudo()
        cls.Partner = cls.env["res.partner"]

        cls.vehicle_product = cls.ProductProduct.create(
            {
                "name": "Test Vehicle",
                "type": "consu",
                "is_storable": True,
                "tracking": "serial",
                "asset_kind_id": cls.env.ref("base.kind_vehicle").id,
            }
        )
        cls.fuel_product = cls.ProductProduct.create(
            {
                "name": "Diesel Fuel",
                "type": "service",
                "standard_price": 1.50,
            }
        )
        cls.vehicle = cls.ProductTrace.create(
            {
                "name": "VH-TEST-001",
                "product_id": cls.vehicle_product.id,
                "company_id": cls.test_company.id,
            }
        )
        cls.vendor = cls.Partner.create(
            {
                "name": "Fuel Supplier",
                "is_company": True,
            }
        )

    def _create_fuel_bill(self, product=None, currency=None, with_asset=True):
        company = self.test_company
        move_form = Form(
            self.AccountMove.with_company(company).with_context(
                default_move_type="in_invoice",
                default_journal_id=self.purchase_journal.id,
                default_company_id=company.id,
            )
        )
        move_form.partner_id = self.vendor
        move_form.invoice_date = "2024-01-15"
        if currency:
            move_form.currency_id = currency
        with move_form.invoice_line_ids.new() as line_form:
            line_form.product_id = product or self.fuel_product
            line_form.account_id = self.expense_account
            if with_asset:
                line_form.asset_id = self.vehicle.asset_id
            line_form.quantity = 50.0
            line_form.price_unit = 1.50
            line_form.tax_ids.clear()
        move = move_form.save()
        line = move.invoice_line_ids[:1]
        return move, line, line.asset_log_ids

    def _fuel_spend(self):
        self.vehicle.asset_id.invalidate_recordset(["log_ids"])
        logs = self.vehicle.asset_id.log_ids.filtered(
            lambda log: log.log_type == "fuel" and log.state == "done"
        )
        return sum(logs.mapped("amount"))

    def test_asset_sync_from_move_line(self):
        _, _, log = self._create_fuel_bill()
        self.assertEqual(log.trace_id, self.vehicle)

    def test_amount_sync_from_move_line(self):
        _, line, log = self._create_fuel_bill()
        self.assertEqual(log.amount, line.price_subtotal)

    def test_amount_uses_company_currency_on_foreign_bill(self):
        foreign_currency = self.setup_other_currency("EUR", rates=[("2024-01-01", 0.5)])
        move, line, log = self._create_fuel_bill(currency=foreign_currency)

        self.assertEqual(move.currency_id, foreign_currency)
        self.assertNotEqual(line.price_subtotal, abs(line.balance))
        self.assertEqual(log.currency_id, self.test_company.currency_id)
        self.assertEqual(log.amount, abs(line.balance))

    def test_manual_amount_survives_unlink_from_bill(self):
        _, _, log = self._create_fuel_bill()
        billed_amount = log.amount
        self.assertTrue(billed_amount)

        log.write({"account_move_line_id": False})

        self.assertFalse(log.account_move_line_id)
        self.assertEqual(log.amount, billed_amount)

    def test_amount_readonly_when_linked_to_bill(self):
        _, _, log = self._create_fuel_bill()
        with self.assertRaises(UserError):
            log.write({"amount": 100.0})

    def test_delete_bill_linked_log_prevented(self):
        _, _, log = self._create_fuel_bill()
        with self.assertRaises(UserError):
            log.unlink()

    def test_manual_log_can_be_deleted(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.vehicle.asset_id.id,
                "product_id": self.fuel_product.id,
            }
        )
        log.unlink()
        self.assertFalse(log.exists())

    def test_action_view_account_move(self):
        move, _, log = self._create_fuel_bill()
        action = log.action_view_account_move()
        self.assertEqual(action["res_model"], "account.move")
        self.assertEqual(action["res_id"], move.id)
        self.assertEqual(action["view_mode"], "form")

    def test_bill_state_field(self):
        move, _, log = self._create_fuel_bill()
        self.assertEqual(log.account_move_state, "draft")
        move.action_post()
        self.assertEqual(log.account_move_state, "posted")

    def test_linked_log_state_starts_new_on_draft_bill(self):
        _, _, log = self._create_fuel_bill()
        self.assertEqual(log.state, "new")

    def test_linked_log_state_flips_to_done_on_post(self):
        move, _, log = self._create_fuel_bill()
        move.action_post()
        self.assertEqual(log.state, "done")

    def test_linked_log_state_flips_to_cancelled_on_bill_cancel(self):
        move, _, log = self._create_fuel_bill()
        move.action_post()
        move.action_cancel()
        self.assertEqual(log.state, "cancelled")

    def test_linked_log_state_resets_to_new_on_bill_reset_to_draft(self):
        move, _, log = self._create_fuel_bill()
        move.action_post()
        self.assertEqual(log.state, "done")
        move.action_draft()
        self.assertEqual(log.state, "new")

    def test_a_log_for_a_line_of_a_posted_bill_starts_done(self):
        move, line, _ = self._create_fuel_bill(with_asset=False)
        move.action_post()

        line.asset_id = self.vehicle.asset_id

        self.assertEqual(line.asset_log_ids.state, "done")
        self.assertEqual(str(line.asset_log_ids.date), "2024-01-15")

    def test_a_manual_log_starts_new_on_today(self):
        log = self.ProductAssetLog.create(
            {"asset_id": self.vehicle.asset_id.id, "product_id": self.fuel_product.id}
        )

        self.assertEqual(log.state, "new")
        self.assertEqual(log.date, fields.Date.context_today(log))

    def test_manual_log_state_is_not_touched_by_compute(self):
        log = self.ProductAssetLog.create(
            {
                "asset_id": self.vehicle.asset_id.id,
                "product_id": self.fuel_product.id,
                "state": "done",
            }
        )
        self.assertEqual(log.state, "done")
        log.write({"state": "cancelled"})
        self.assertEqual(log.state, "cancelled")

    def test_fuel_balance_reflects_bill_post_and_cancel(self):
        fuel_category = self.env.ref("asset_ledger.product_category_fuel")
        balance_fuel_product = self.ProductProduct.create(
            {
                "name": "Fuel (balance test)",
                "type": "service",
                "standard_price": 1.50,
                "categ_id": fuel_category.id,
            }
        )
        self.assertEqual(self._fuel_spend(), 0.0)

        move, line, _ = self._create_fuel_bill(product=balance_fuel_product)
        self.assertEqual(
            self._fuel_spend(), 0.0, "Draft bill must not move the fuel spend."
        )

        move.action_post()
        self.assertEqual(
            self._fuel_spend(),
            line.price_subtotal,
            "Posted bill should book the line subtotal as fuel spend.",
        )

        move.action_cancel()
        self.assertEqual(self._fuel_spend(), 0.0, "Cancelled bill should book nothing.")

    def test_rebate_line_reduces_the_asset_spend(self):
        fuel_category = self.env.ref("asset_ledger.product_category_fuel")
        rebate_fuel_product = self.ProductProduct.create(
            {
                "name": "Fuel (rebate test)",
                "type": "service",
                "standard_price": 1.0,
                "categ_id": fuel_category.id,
            }
        )
        move_form = Form(
            self.AccountMove.with_company(self.test_company).with_context(
                default_move_type="in_invoice",
                default_journal_id=self.purchase_journal.id,
                default_company_id=self.test_company.id,
            )
        )
        move_form.partner_id = self.vendor
        move_form.invoice_date = "2024-01-15"
        for price in (300.0, -100.0):
            with move_form.invoice_line_ids.new() as line_form:
                line_form.product_id = rebate_fuel_product
                line_form.account_id = self.expense_account
                line_form.asset_id = self.vehicle.asset_id
                line_form.quantity = 1.0
                line_form.price_unit = price
                line_form.tax_ids.clear()
        move = move_form.save()
        # A negative *total* cannot be posted at all, so the reachable shape of a
        # credit is a rebate line inside a bill that is still positive overall.
        move.action_post()

        logs = move.invoice_line_ids.asset_log_ids
        self.assertEqual(
            sorted(logs.mapped("amount")),
            [-100.0, 300.0],
            "The log keeps the sign of the bill line it mirrors",
        )

        self.assertEqual(
            self._fuel_spend(),
            200.0,
            "The fuel card is debited by what was spent, not by the gross of "
            "the expense line plus the rebate",
        )
