from odoo import Command
from odoo.exceptions import RedirectWarning, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged

from .common import CreditAuthorizationCase


@tagged("post_install", "-at_install")
class TestCreditLimitEnforcement(CreditAuthorizationCase, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._old_categ_states = {}
        if "approval.category" in cls.env:
            sale_categories = cls.env["approval.category"].search(
                [("approval_type", "=", "sale")]
            )
            cls._old_categ_states = {c.id: c.active for c in sale_categories}
            sale_categories.write({"active": False})

        cls._old_validation_level = None
        if "so_validation_level" in cls.env["res.company"]._fields:
            cls._old_validation_level = cls.env.company.so_validation_level
            cls.env.company.write({"so_validation_level": "none"})

        cls.user = cls.env["res.users"].create(
            {
                "name": "Credit Limit Enforcement Manager",
                "login": "test_credit_limit_enforcement",
                "email": "test_credit_limit_enforcement@example.com",
                "company_id": cls.env.company.id,
                "company_ids": [Command.link(cls.env.company.id)],
                "group_ids": [
                    Command.link(cls.env.ref("sale.group_sale_salesman").id),
                    Command.link(cls.env.ref("account_credit.group_credit_manager").id),
                ],
            }
        )
        cls.unconditional_type = cls.env["credit.grade"].create(
            {"name": "Enforcement Unconditional"}
        )
        cls.partner = cls.env["res.partner"].create({"name": "Enforcement Partner"})
        cls.partner.write(
            {
                "credit_grade_id": cls.unconditional_type.id,
                "credit_trusted_amount": 10000.0,
            }
        )
        cls.credit_term = cls.env["account.payment.term"].create(
            {
                "name": "Enforcement 30 Days",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100.0, "nb_days": 30}
                    )
                ],
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Enforcement Product", "list_price": 1000.0}
        )

    @classmethod
    def tearDownClass(cls):
        if cls._old_validation_level is not None:
            cls.env.company.write({"so_validation_level": cls._old_validation_level})
        for cat_id, active in cls._old_categ_states.items():
            cls.env["approval.category"].browse(cat_id).write({"active": active})
        super().tearDownClass()

    def _create_order(self, price, partner=None):
        return (
            self.env["sale.order"]
            .with_user(self.user)
            .create(
                {
                    "partner_id": (partner or self.partner).id,
                    "payment_term_id": self.credit_term.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_qty": 1.0,
                                "price_unit": price,
                            }
                        )
                    ],
                }
            )
        )

    def _wizard_from(self, orders):
        return self._credit_authorization_wizard(orders)

    def test_sequential_confirm_blocks_on_cumulative_exposure(self):
        limit = self.partner.credit_limit
        self.assertEqual(limit, 10000.0)
        order = self._create_order(price=limit / 4.0)
        exposure = order._get_credit_exposure()
        self.assertLess(exposure, limit, "one order alone must fit in the limit")

        committed = 0.0
        while committed + exposure <= limit:
            self.assertFalse(
                order._is_credit_limit_exceeded(),
                "an order that fits in the remaining limit must not be blocked",
            )
            order.action_confirm()
            self.assertEqual(order.state, "done")
            committed += exposure
            order = self._create_order(price=limit / 4.0)

        self.assertGreater(committed, 0.0, "at least one order must have confirmed")
        self.partner.invalidate_recordset(["credit"])
        self.assertEqual(
            self.partner.credit,
            0.0,
            "no invoice was issued, so the receivable balance sees nothing",
        )
        self.assertTrue(
            order._is_credit_limit_exceeded(),
            "a confirmed but uninvoiced order still consumes the credit limit: "
            f"{committed} already committed plus {exposure} against a {limit} limit",
        )
        with self.assertRaises(RedirectWarning):
            order.action_confirm()
        self.assertEqual(order.state, "draft")

    def test_an_order_on_a_draft_invoice_stands_once_in_the_exposure(self):
        self.product.invoice_policy = "ordered"
        order = self._create_order(price=3000.0)
        order.action_confirm()
        profile = order._credit_profile()
        committed = profile._invalidate_exposure().exposure_total
        self.assertEqual(committed, order.amount_total)

        invoice = order.sudo()._create_invoices()

        profile._invalidate_exposure()
        self.assertEqual(profile.exposure_draft, order.amount_total)
        self.assertEqual(profile.exposure_uninvoiced, 0.0)
        self.assertEqual(profile.exposure_total, committed)

        invoice.action_post()

        profile._invalidate_exposure()
        self.assertEqual(profile.exposure_open, order.amount_total)
        self.assertEqual(profile.exposure_draft, 0.0)
        self.assertEqual(profile.exposure_uninvoiced, 0.0)
        self.assertEqual(profile.exposure_total, committed)

    def test_batch_confirm_blocks_on_aggregate_exposure(self):
        limit = self.partner.credit_limit
        orders = self.env["sale.order"].with_user(self.user)
        for _ in range(3):
            orders |= self._create_order(price=limit / 2.5)
        for order in orders:
            self.assertLess(
                order._get_credit_exposure(),
                limit,
                "each order of the batch must be individually within the limit",
            )
        self.assertGreater(
            sum(order._get_credit_exposure() for order in orders),
            limit,
            "the batch must be over the limit in aggregate",
        )
        self.assertEqual(
            len(orders._get_orders_needing_credit_authorization()),
            1,
            "only the order that crosses the running total may be blocked",
        )
        with self.assertRaises(RedirectWarning):
            orders.action_confirm()
        self.assertEqual(orders.mapped("state"), ["draft"] * 3)
        wizard = self._wizard_from(orders)
        self.assertEqual(
            wizard.order_ids,
            orders._get_orders_needing_credit_authorization(),
            "the module's own batch path must route the excess to the wizard",
        )
        self.assertEqual(wizard.safe_order_ids, orders - wizard.order_ids)
        total = sum(order._get_credit_exposure() for order in orders)
        self.assertAlmostEqual(
            wizard.amount_authorized,
            total - limit,
            places=2,
            msg="the authorization must cover every order the wizard will "
            "confirm, not only the one that tripped the running total",
        )
        wizard.action_authorize_confirm()
        self.assertEqual(orders.mapped("state"), ["done"] * 3)

    def test_zeroed_authorization_must_not_confirm(self):
        order = self._create_order(price=self.partner.credit_limit * 1.5)
        wizard = self._wizard_from(order)
        self.assertGreater(wizard.amount_authorized, 0.0)
        wizard.amount_authorized = 0.0

        authorizations = self.env["credit.facility"].search_count([])
        with self.assertRaises(UserError):
            wizard.action_authorize_confirm()
        self.assertEqual(
            order.state, "draft", "an unauthorized excess must not be confirmed"
        )
        self.assertEqual(
            self.env["credit.facility"].search_count([]),
            authorizations,
            "no authorization was recorded, so nothing may be confirmed",
        )

    def test_covering_authorization_still_confirms(self):
        order = self._create_order(price=self.partner.credit_limit * 1.5)
        wizard = self._wizard_from(order)
        wizard.action_authorize_confirm()
        self.assertEqual(order.state, "done")
        self.assertEqual(
            self.env["credit.facility"].search_count(
                [("partner_id", "=", self.partner.id), ("source", "=", "authorization")]
            ),
            1,
            "the authorized excess must leave exactly one audit record",
        )

    def test_legal_hold_is_settable_on_exception_partner(self):
        partner = self.env["res.partner"].create(
            {"name": "Exception Then Legal", "credit_exception": True}
        )
        self.assertEqual(partner.credit_status, "authorized")

        partner.action_toggle_legal()
        self.assertTrue(partner.credit_legal_hold)
        self.assertFalse(
            partner.credit_exception,
            "legal process wins, so it clears the exception it overrides",
        )
        self.assertEqual(partner.credit_status, "legal")

        with self.assertRaises(ValidationError):
            partner.credit_exception = True
            partner.flush_recordset()

    def test_invoiced_order_authorization_stops_granting_limit(self):
        self.product.invoice_policy = "ordered"
        baseline = self.partner.credit_limit
        order = self._create_order(price=baseline * 1.5)
        record = self._wizard_from(order).action_authorize()
        order.with_context(credit_override=True).action_confirm()
        self.partner.invalidate_recordset(["credit_limit"])
        self.assertGreater(self.partner.credit_limit, baseline)

        invoice = order.sudo()._create_invoices()
        self.partner.invalidate_recordset(["credit_limit"])
        self.assertGreater(
            self.partner.credit_limit,
            baseline,
            "a draft invoice still leaves the order open",
        )

        invoice.with_context(credit_override=True).action_post()
        self.assertEqual(order.invoice_state, "done")
        self.partner.invalidate_recordset(["credit_limit"])
        self.assertEqual(
            self.partner.credit_limit,
            baseline,
            "once posted, the excess is receivable and the authorization covers "
            "no open order",
        )
        self.assertFalse(record._is_granting())

    def test_cancelled_order_authorization_stops_granting_limit(self):
        baseline = self.partner.credit_limit
        order = self._create_order(price=baseline * 1.5)
        record = self._wizard_from(order).action_authorize()
        self.assertTrue(record, "authorizing an excess must leave a record")
        self.assertEqual(record.order_ids, order)
        self.partner.invalidate_recordset(["credit_limit"])
        self.assertGreater(self.partner.credit_limit, baseline)

        order._action_cancel()
        self.assertEqual(order.state, "cancel")
        self.partner.invalidate_recordset(["credit_limit"])
        self.assertEqual(
            self.partner.credit_limit,
            baseline,
            "an authorization whose orders are all cancelled covered nothing",
        )
        self.assertTrue(
            record.active, "the decision stays on file so it remains auditable"
        )

    def test_batch_authorization_records_every_order(self):
        limit = self.partner.credit_limit
        orders = self.env["sale.order"].with_user(self.user)
        for _ in range(2):
            orders |= self._create_order(price=limit * 1.5)
        record = self._wizard_from(orders).action_authorize()
        self.assertEqual(
            record.order_ids,
            orders,
            "every order the authorization covered must be recorded",
        )
