from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEnsureCreditAllowed(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Ensure Test Partner"})

    def test_ensure_legal_raises(self):
        self.partner.write({"credit_legal_hold": True})
        with self.assertRaises(ValidationError):
            self.partner._check_credit_allowed(immediate=True)
        with self.assertRaises(ValidationError):
            self.partner._check_credit_allowed(immediate=False)

    def test_ensure_cash_non_immediate_raises(self):
        self.partner.write({"credit_status": "cash"})
        with self.assertRaises(ValidationError):
            self.partner._check_credit_allowed(immediate=False)

    def test_ensure_cash_immediate_passes(self):
        self.partner.write({"credit_status": "cash"})
        self.partner._check_credit_allowed(immediate=True)

    def test_ensure_review_passes(self):
        self.partner.write({"credit_status": "review"})
        self.partner._check_credit_allowed(immediate=True)
        self.partner._check_credit_allowed(immediate=False)

    def test_ensure_authorized_passes(self):
        self.partner.write({"credit_status": "authorized"})
        self.partner._check_credit_allowed(immediate=True)
        self.partner._check_credit_allowed(immediate=False)


@tagged("post_install", "-at_install")
class TestRequiresCreditApproval(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Restricted Test"})

    def test_requires_approval_legal(self):
        self.partner.write({"credit_legal_hold": True})
        self.assertFalse(self.partner._is_credit_approval_required(immediate=True))
        self.assertFalse(self.partner._is_credit_approval_required(immediate=False))

    def test_requires_approval_cash_immediate(self):
        self.partner.write({"credit_status": "cash"})
        self.assertFalse(self.partner._is_credit_approval_required(immediate=True))

    def test_requires_approval_cash_non_immediate(self):
        self.partner.write({"credit_status": "cash"})
        self.assertFalse(self.partner._is_credit_approval_required(immediate=False))

    def test_requires_approval_review_non_immediate(self):
        self.partner.write({"credit_status": "review"})
        self.assertTrue(self.partner._is_credit_approval_required(immediate=False))

    def test_requires_approval_review_immediate(self):
        self.partner.write({"credit_status": "review"})
        self.assertFalse(self.partner._is_credit_approval_required(immediate=True))

    def test_requires_approval_authorized_no_exception(self):
        self.partner.write({"credit_status": "authorized", "credit_exception": False})
        self.assertFalse(self.partner._is_credit_approval_required(immediate=True))
        self.assertFalse(self.partner._is_credit_approval_required(immediate=False))

    def test_requires_approval_exception_non_immediate(self):
        self.partner.write({"credit_exception": True})
        self.assertFalse(
            self.partner._is_credit_approval_required(immediate=False),
            "a dated exception allows credit on its own; its review is the control",
        )

    def test_requires_approval_exception_immediate(self):
        self.partner.write({"credit_exception": True})
        self.assertFalse(self.partner._is_credit_approval_required(immediate=True))


@tagged("post_install", "-at_install")
class TestValidateCreditStatusRefactored(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Validate Test"})

    def test_validate_legal_raises(self):
        self.partner.write({"credit_legal_hold": True})
        with self.assertRaises(ValidationError):
            self.partner._check_credit_status(immediate=False)

    def test_validate_cash_non_immediate_raises(self):
        self.partner.write({"credit_status": "cash"})
        with self.assertRaises(ValidationError):
            self.partner._check_credit_status(immediate=False)

    def test_validate_cash_immediate_passes(self):
        self.partner.write({"credit_status": "cash"})
        self.assertTrue(self.partner._check_credit_status(immediate=True))

    def test_validate_review_non_immediate_raises(self):
        self.partner.write({"credit_status": "review", "credit_exception": False})
        with self.assertRaises(ValidationError):
            self.partner._check_credit_status(immediate=False)

    def test_validate_review_immediate_passes(self):
        self.partner.write({"credit_status": "review"})
        self.assertTrue(self.partner._check_credit_status(immediate=True))

    def test_validate_exception_bypasses(self):
        self.partner.write({"credit_exception": True})
        self.assertTrue(self.partner._check_credit_status(immediate=False))

    def test_validate_authorized_passes(self):
        self.partner.write({"credit_exception": True})
        self.assertEqual(self.partner.credit_status, "authorized")
        self.assertTrue(self.partner._check_credit_status(immediate=False))


@tagged("post_install", "-at_install")
class TestConstraintC2C3(TransactionCase):
    def test_constraint_c2_legal_wins_over_exception(self):
        partner = self.env["res.partner"].create(
            {
                "name": "C2 Test",
                "credit_exception": True,
            }
        )
        partner.write({"credit_legal_hold": True})
        self.assertFalse(
            partner.credit_exception,
            "legal process wins, so it clears the exception it overrides",
        )
        self.assertEqual(partner.credit_status, "legal")

    def test_constraint_c3_exception_on_legal_raises(self):
        partner = self.env["res.partner"].create({"name": "C3 Test"})
        partner.write({"credit_legal_hold": True})
        with self.assertRaises(ValidationError):
            partner.write({"credit_exception": True})

    def test_constraint_c2c3_both_cleared_then_legal_ok(self):
        partner = self.env["res.partner"].create(
            {
                "name": "C2C3 Test",
                "credit_exception": True,
            }
        )
        partner.write({"credit_exception": False})
        partner.write({"credit_legal_hold": True})
        self.assertEqual(partner.credit_status, "legal")

    def test_constraint_c1_exception_moves_to_authorized(self):
        partner = self.env["res.partner"].create({"name": "C1 Test"})
        self.assertFalse(partner.credit_status)
        partner.write({"credit_exception": True})
        self.assertEqual(partner.credit_status, "authorized")


@tagged("post_install", "-at_install")
class TestCanConfirmCommercialPartner(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.commercial = cls.env["res.partner"].create({"name": "Commercial Parent"})
        cls.contact = cls.env["res.partner"].create(
            {
                "name": "Contact Child",
                "parent_id": cls.commercial.id,
                "type": "contact",
            }
        )
        cls.credit_term = cls.env["account.payment.term"].create(
            {
                "name": "Commercial 30 Days",
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
        cls.product = cls.env["product.product"].create(
            {
                "name": "Commercial Test Product",
                "list_price": 100.0,
            }
        )
        cls.user = cls.env["res.users"].create(
            {
                "name": "Commercial Test User",
                "login": "test_commercial_credit",
                "email": "test_commercial_credit@example.com",
                "group_ids": [
                    Command.link(cls.env.ref("sale.group_sale_salesman").id),
                ],
            }
        )

    def test_can_confirm_uses_commercial_partner(self):
        self.commercial.write({"credit_legal_hold": True})
        order = (
            self.env["sale.order"]
            .with_user(self.user)
            .create(
                {
                    "partner_id": self.contact.id,
                    "payment_term_id": self.credit_term.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": self.product.id,
                                "product_qty": 1.0,
                            }
                        )
                    ],
                }
            )
        )
        with self.assertRaises(ValidationError):
            order._check_confirm_credit_status()
