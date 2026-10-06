from odoo import Command
from odoo.tests import new_test_user, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account_credit.models.credit_utils import CreditRefused


@tagged("post_install", "-at_install")
class TestCreditStanding(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.Profile = cls.env["credit.profile"].sudo()
        cls.billing_user = new_test_user(
            cls.env,
            login="credit_standing_billing",
            groups="account.group_account_invoice",
            company_id=cls.company.id,
        )
        cls.salesperson = new_test_user(
            cls.env,
            login="credit_standing_salesperson",
            groups="sale.group_sale_salesman",
            company_id=cls.company.id,
        )
        cls.stock_user = new_test_user(
            cls.env,
            login="credit_standing_stock",
            groups="stock.group_stock_user",
            company_id=cls.company.id,
        )
        if "so_validation_level" in cls.company._fields:
            cls.company.sudo().so_validation_level = "none"
        cls.storable = cls.env["product.product"].create(
            {"name": "Credit Standing Goods", "is_storable": True, "list_price": 100.0}
        )
        warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.env["stock.quant"].sudo().with_company(
            cls.company
        )._update_available_quantity(cls.storable, warehouse.lot_stock_id, 10)
        if "can_validate_user_ids" in warehouse.out_type_id._fields:
            # marin lets only the users its operation types list validate
            # their transfers: the stock user validates as one of them
            warehouse.out_type_id.sudo().can_validate_user_ids = [
                Command.link(cls.stock_user.id)
            ]

    def _profile(self, partner):
        return self.Profile._for_partner(partner, company=self.company)

    def _give_standing(self, partner):
        return self.Profile._for_partner(partner, company=self.company, create=True)

    def _credit_invoice(self, partner=None):
        partner = partner or self.partner_b
        return self.init_invoice(
            "out_invoice", partner=partner, invoice_date="2024-01-01", amounts=[1000.0]
        )

    def _credit_order(self, user):
        return (
            self.env["sale.order"]
            .with_user(user)
            .create(
                {
                    "partner_id": self.partner_b.id,
                    "payment_term_id": self.pay_terms_b.id,
                    "line_ids": [
                        Command.create(
                            {"product_id": self.storable.id, "product_qty": 1}
                        )
                    ],
                }
            )
        )

    def test_a_partner_without_standing_is_invoiced_on_credit(self):
        invoice = self._credit_invoice().with_user(self.billing_user)
        self.assertEqual(invoice.invoice_payment_term_id, self.pay_terms_b)
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")
        self.assertFalse(self._profile(self.partner_b), "checking gave no standing")

    def test_a_partner_without_standing_has_no_status_and_no_verdict(self):
        order = self._credit_order(self.salesperson)
        self.assertFalse(order.credit_verdict_outcome)
        self.assertFalse(order.approval_required)
        partner = self.partner_b.with_company(self.company)
        self.assertFalse(partner.credit_status)
        self.assertIn(
            partner, partner.search([("credit_status", "=", False)]), "searchable"
        )
        self.assertFalse(self._profile(self.partner_b))

    def test_a_billing_user_sees_the_credit_warning_of_a_hand_set_limit(self):
        self.company.sudo().account_config_id.account_use_credit_limit = True
        self.partner_b.with_company(self.company).sudo().credit_limit = 100.0
        invoice = self._credit_invoice().with_user(self.billing_user)
        self.assertIn("credit limit", invoice.partner_credit_warning)

    def test_a_partner_with_standing_is_refused_credit(self):
        self._give_standing(self.partner_b)
        invoice = self._credit_invoice().with_user(self.billing_user)
        with self.assertRaisesRegex(CreditRefused, "cash-only"):
            invoice.action_post()

    def test_a_partner_with_standing_still_pays_immediately(self):
        self._give_standing(self.partner_a)
        invoice = self._credit_invoice(self.partner_a)
        self.assertEqual(invoice.invoice_payment_term_id, self.pay_terms_a)
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")

    def test_a_salesperson_confirms_on_credit_without_standing(self):
        order = self._credit_order(self.salesperson)
        order.action_confirm()
        self.assertIn(order.state, ("sale", "done"))

    def test_a_salesperson_is_refused_credit_for_a_partner_with_standing(self):
        self._give_standing(self.partner_b)
        order = self._credit_order(self.salesperson)
        with self.assertRaisesRegex(CreditRefused, "cash-only"):
            order.action_confirm()

    def test_a_stock_user_validates_a_credit_delivery(self):
        order = self._credit_order(self.salesperson)
        order.action_confirm()
        picking = order.picking_ids.with_user(self.stock_user)
        self.assertFalse(picking.credit_verdict_outcome, "no standing: no verdict")
        self._give_standing(self.partner_b)
        picking.invalidate_recordset(["credit_verdict_outcome"])
        picking.move_ids.quantity = 1
        picking.move_ids.picked = True
        self.assertTrue(picking.credit_verdict_outcome, "the policy judged it")
        picking.button_validate()
        self.assertEqual(picking.state, "done")

    def test_a_branch_keeper_validates_a_colleagues_credit_delivery(self):
        """A branch's warehouse keeper may sell too, as a seller reading their
        own orders only: the delivery of a colleague's order still weighs its
        credit, opened and validated, and the order stays out of their reach."""
        keeper = new_test_user(
            self.env,
            login="credit_standing_keeper",
            groups="sale.group_sale_salesman,stock.group_stock_user",
            company_id=self.company.id,
        )
        out_type = (
            self.env["stock.warehouse"]
            .search([("company_id", "=", self.company.id)], limit=1)
            .out_type_id
        )
        if "can_validate_user_ids" in out_type._fields:
            out_type.sudo().can_validate_user_ids = [Command.link(keeper.id)]
        order = self._credit_order(self.salesperson)
        order.action_confirm()
        self._give_standing(self.partner_b)
        self.assertFalse(
            order.with_user(keeper).has_access("read"),
            "a colleague's order stays out of the keeper's reach",
        )
        picking = order.picking_ids.with_user(keeper)
        # the keeper opens the delivery in a request of their own: nothing the
        # salesperson read is cached, and a cached value is read unchecked
        self.env.invalidate_all()
        self.assertTrue(picking.credit_verdict_outcome, "the keeper opens it judged")
        picking.move_ids.quantity = 1
        picking.move_ids.picked = True
        self.env.invalidate_all()
        picking.button_validate()
        self.assertEqual(picking.state, "done")
