from odoo import Command, models
from odoo.exceptions import RedirectWarning, ValidationError
from odoo.tests.common import TransactionCase, tagged

from .common import CreditAuthorizationCase
from odoo.addons.approval.tests.common import pool_step


@tagged("post_install", "-at_install")
class TestCreditApproval(CreditAuthorizationCase, TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.immediate_term = cls.env["account.payment.term"].create(
            {
                "name": "Bridge Immediate",
                "line_ids": [
                    Command.create(
                        {
                            "value": "percent",
                            "value_amount": 100.0,
                            "nb_days": 0,
                        }
                    )
                ],
            }
        )
        cls.credit_term = cls.env["account.payment.term"].create(
            {
                "name": "Bridge 30 Days",
                "line_ids": [
                    Command.create(
                        {
                            "value": "percent",
                            "value_amount": 100.0,
                            "nb_days": 30,
                        }
                    )
                ],
            }
        )

        existing_categories = cls.env["approval.category"].search(
            [
                ("approval_type", "=", "sale"),
            ]
        )
        cls._old_categ_states = {c.id: c.active for c in existing_categories}
        existing_categories.write({"active": False})

        cls._old_validation_level = cls.env.company.so_validation_level
        cls.env.company.write({"so_validation_level": "none"})

        cls.approval_category = cls.env["approval.category"].create(
            {
                "name": "Bridge Test Approval",
                "approval_type": "sale",
                "target_model": False,
                "company_id": cls.env.company.id,
                "active": False,
                "order_amount_min": 0.01,
                "order_amount_max": 999999.0,
                "check_credit_limit": False,
                "step_ids": pool_step(
                    [(cls.env.ref("base.user_admin").id, True, 10)], minimum=1
                ),
            }
        )

        cls.credit_type = cls.env["credit.grade"].search(
            [("rule_ids", "!=", False)], limit=1
        )
        cls.unconditional_type = cls.env["credit.grade"].create(
            {"name": "Bridge Unconditional"}
        )

        cls.product = cls.env["product.product"].create(
            {
                "name": "Bridge Product",
                "list_price": 1000.0,
            }
        )

        cls.user = cls.env["res.users"].create(
            {
                "name": "Bridge Test User",
                "login": "test_bridge_credit",
                "email": "test_bridge_credit@example.com",
                "company_id": cls.env.company.id,
                "company_ids": [Command.link(cls.env.company.id)],
                "group_ids": [
                    Command.link(cls.env.ref("sale.group_sale_salesman").id),
                    Command.link(cls.env.ref("account_credit.group_credit_manager").id),
                ],
            }
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.env.company.write({"so_validation_level": cls._old_validation_level})
        for cat_id, active in cls._old_categ_states.items():
            cls.env["approval.category"].browse(cat_id).write({"active": active})
        super().tearDownClass()

    def _activate_category(self) -> None:
        self.approval_category.write({"active": True})
        self.addCleanup(lambda: self.approval_category.write({"active": False}))

    def _make_partner(
        self,
        name: str,
        status: str = "authorized",
        exception: bool = False,
        limit: float = 0.0,
    ) -> models.Model:
        vals = {"name": name, "credit_exception": exception}
        if status == "review" and self.credit_type:
            vals["credit_grade_id"] = self.credit_type.id
        if status == "legal":
            vals["credit_legal_hold"] = True
        if limit:
            vals["credit_trusted_amount"] = limit
        if status == "authorized" and not exception:
            vals["credit_grade_id"] = self.unconditional_type.id
        partner = self.env["res.partner"].create(vals)
        partner.invalidate_recordset()
        self.assertEqual(partner.credit_status, status)
        return partner

    def _make_order(
        self,
        partner: models.Model,
        term: models.Model | None = None,
        price: float | None = None,
    ) -> models.Model:
        return (
            self.env["sale.order"]
            .with_user(self.user)
            .create(
                {
                    "partner_id": partner.id,
                    "payment_term_id": (term or self.credit_term).id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_qty": 1.0,
                                "price_unit": price or 1000.0,
                            }
                        )
                    ],
                }
            )
        )

    def test_d1_legal_immediate_hard_block(self) -> None:
        partner = self._make_partner("D1", status="legal")
        order = self._make_order(partner, term=self.immediate_term)
        with self.assertRaises(ValidationError):
            order.action_confirm()

    def test_d2_legal_immediate_limit_exceeded_hard_block(self) -> None:
        partner = self._make_partner("D2", status="legal", limit=500.0)
        order = self._make_order(partner, term=self.immediate_term, price=1000.0)
        with self.assertRaises(ValidationError):
            order.action_confirm()

    def test_d3_legal_non_immediate_hard_block(self) -> None:
        partner = self._make_partner("D3", status="legal")
        order = self._make_order(partner)
        with self.assertRaises(ValidationError):
            order.action_confirm()

    def test_d4_legal_non_immediate_limit_exceeded_hard_block(self) -> None:
        partner = self._make_partner("D4", status="legal", limit=500.0)
        order = self._make_order(partner, price=1000.0)
        with self.assertRaises(ValidationError):
            order.action_confirm()

    def test_d5_cash_immediate_confirms(self) -> None:
        partner = self._make_partner("D5", status="cash")
        order = self._make_order(partner, term=self.immediate_term)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_d6_cash_immediate_limit_exceeded_confirms(self) -> None:
        partner = self._make_partner("D6", status="cash", limit=500.0)
        order = self._make_order(partner, term=self.immediate_term, price=1000.0)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_d7_cash_non_immediate_error(self) -> None:
        partner = self._make_partner("D7", status="cash")
        order = self._make_order(partner)
        with self.assertRaises(ValidationError):
            order.action_confirm()

    def test_d8_cash_non_immediate_limit_exceeded_error(self) -> None:
        partner = self._make_partner("D8", status="cash", limit=500.0)
        order = self._make_order(partner, price=1000.0)
        with self.assertRaises(ValidationError):
            order.action_confirm()

    def test_d9_review_immediate_confirms(self) -> None:
        partner = self._make_partner("D9", status="review")
        order = self._make_order(partner, term=self.immediate_term)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_d10_review_immediate_limit_exceeded_confirms(self) -> None:
        partner = self._make_partner("D10", status="review", limit=500.0)
        order = self._make_order(partner, term=self.immediate_term, price=1000.0)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_d11_review_non_immediate_approval(self) -> None:
        self._activate_category()
        partner = self._make_partner("D11", status="review")
        order = self._make_order(partner)
        self.assertTrue(order.approval_required)

    def test_an_approved_order_carries_its_approval_to_its_invoice(self) -> None:
        self._activate_category()
        self.product.invoice_policy = "ordered"
        partner = self._make_partner("Carried", status="review", limit=50000.0)
        order = self._make_order(partner)
        self.assertTrue(order.approval_required)
        order.action_confirm()
        request = order.approval_request_id
        self.assertTrue(request)
        request.with_user(self.env.ref("base.user_admin")).action_approve()
        self.assertEqual(order.approval_state, "approved")
        if order.state == "draft":
            order.action_confirm()
        self.assertEqual(order.state, "done")

        invoice = order.sudo()._create_invoices()
        invoice.action_post()
        self.assertEqual(
            invoice.state,
            "posted",
            "the conditions approved on the order are not asked again on its invoice",
        )

        stand_alone = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "invoice_payment_term_id": self.credit_term.id,
                "invoice_line_ids": [
                    Command.create({"product_id": self.product.id, "price_unit": 100.0})
                ],
            }
        )
        with self.assertRaises(ValidationError):
            stand_alone.action_post()

    def test_d12_review_non_immediate_no_tier(self) -> None:
        partner = self._make_partner("D12", status="review")
        order = self._make_order(partner, price=100.0)
        with self.assertRaises(RedirectWarning):
            order.action_confirm()

    def test_d15_authorized_immediate_confirms(self) -> None:
        partner = self._make_partner("D15")
        order = self._make_order(partner, term=self.immediate_term)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_d16_authorized_immediate_limit_exceeded_confirms(self) -> None:
        partner = self._make_partner("D16", limit=500.0)
        order = self._make_order(partner, term=self.immediate_term, price=1000.0)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_d17_authorized_non_immediate_confirms(self) -> None:
        partner = self._make_partner("D17", limit=5000.0)
        order = self._make_order(partner)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_d18_authorized_non_immediate_wizard(self) -> None:
        partner = self._make_partner("D18", limit=500.0)
        order = self._make_order(partner, price=1000.0)
        self._credit_authorization_action(order)

    def test_d18b_action_confirm_raises_instead_of_returning_the_wizard(self) -> None:
        partner = self._make_partner("D18B", limit=500.0)
        order = self._make_order(partner, price=1000.0)
        with self.assertRaises(RedirectWarning):
            order.action_confirm()
        self.assertEqual(order.state, "draft")

    def test_d19_exception_immediate_confirms(self) -> None:
        partner = self._make_partner("D19", exception=True)
        order = self._make_order(partner, term=self.immediate_term)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_d20_exception_immediate_limit_exceeded_confirms(self) -> None:
        partner = self._make_partner("D20", exception=True, limit=500.0)
        order = self._make_order(partner, term=self.immediate_term, price=1000.0)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_d21_exception_non_immediate_needs_no_approval(self) -> None:
        self._activate_category()
        partner = self._make_partner("D21", exception=True)
        order = self._make_order(partner)
        self.assertFalse(
            order.approval_required,
            "a dated exception allows credit; its reclassification review is the control",
        )

    def test_d22_exception_non_immediate_confirms(self) -> None:
        partner = self._make_partner("D22", exception=True)
        order = self._make_order(partner, price=100.0)
        order.action_confirm()
        self.assertEqual(order.state, "done")

    def test_validation_chain_keeps_the_credit_check(self) -> None:
        order = self._make_order(self._make_partner("Chain"))
        methods = order._get_confirm_validation_methods()
        self.assertIn("_check_confirm_credit_status", methods)
        self.assertTrue(order._credit_approval_exempt())

    def test_pre_init_hook_clears_check_credit_limit(self) -> None:
        categories = self.env["approval.category"].search(
            [
                ("check_credit_limit", "=", True),
            ]
        )
        self.assertFalse(categories)

    def test_approval_reason_has_credit_info(self) -> None:
        self._activate_category()
        partner = self._make_partner("Reason", status="review")
        order = self._make_order(partner)
        reason = order._get_approval_reason_html()
        self.assertIn("Credit Status", reason)

    def test_no_payment_term_is_immediate_and_needs_no_approval(self) -> None:
        self._activate_category()
        partner = self._make_partner("NoPT", status="review")
        order = self._make_order(partner)
        order.write({"payment_term_id": False})
        order._compute_approval_required()
        self.assertFalse(order.approval_required)

    def test_credit_limit_zero_is_no_credit_not_unlimited(self) -> None:
        partner = self._make_partner("ZeroLimit")
        self.assertEqual(partner.credit_limit, 0.0)
        order = self._make_order(partner, price=99999.0)
        with self.assertRaises(
            RedirectWarning,
            msg="a partner backed by no guarantees must not be exempt from the "
            "credit limit",
        ):
            order.action_confirm()

    def test_contact_partner_uses_commercial(self) -> None:
        commercial = self._make_partner("Commercial", status="legal")
        contact = self.env["res.partner"].create(
            {
                "name": "Contact",
                "parent_id": commercial.id,
                "type": "contact",
            }
        )
        order = self._make_order(contact)
        with self.assertRaises(ValidationError):
            order.action_confirm()
