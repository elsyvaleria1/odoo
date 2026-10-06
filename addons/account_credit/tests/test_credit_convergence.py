from datetime import timedelta

from odoo import Command
from odoo.exceptions import RedirectWarning, ValidationError
from odoo.fields import Date
from odoo.tests.common import TransactionCase, tagged

from .common import CreditAuthorizationCase


@tagged("post_install", "-at_install")
class CreditScenarioCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._old_categories = {}
        if "approval.category" in cls.env:
            categories = cls.env["approval.category"].search(
                [("approval_type", "=", "sale")]
            )
            cls._old_categories = {c.id: c.active for c in categories}
            categories.write({"active": False})
        if "so_validation_level" in cls.env["res.company"]._fields:
            cls.env.company.so_validation_level = "none"
        documents = cls.env["document.document"]
        cls.root = documents.create({"name": "Convergence Root", "type": "folder"})
        cls.env.company.credit_folder_id = cls.root
        cls.doc_type = cls.env["document.type"].create(
            {"name": "Convergence Type", "code": "CONV_DOC"}
        )
        cls.collateral_type = cls.env["document.type"].create(
            {
                "name": "Convergence Collateral",
                "code": "CONV_COLL",
                "has_collateral": True,
                "has_expiration": True,
            }
        )
        cls.credit_type = cls.env["credit.grade"].create(
            {
                "name": "Convergence Condition",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "one document",
                            "document_type_id": cls.doc_type.id,
                            "min_quantity": 1,
                        }
                    )
                ],
            }
        )
        cls.journal = cls.env["account.journal"].search(
            [("type", "=", "sale"), ("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Convergence Product", "list_price": 1000.0}
        )
        cls.credit_term = cls.env["account.payment.term"].create(
            {
                "name": "Convergence 30 Days",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100.0, "nb_days": 30}
                    )
                ],
            }
        )

    @classmethod
    def tearDownClass(cls):
        for category_id, active in cls._old_categories.items():
            cls.env["approval.category"].browse(category_id).active = active
        super().tearDownClass()

    def _compliant_partner(self, name, extra_documents=()):
        partner = self.env["res.partner"].create({"name": name, "is_company": True})
        partner.credit_grade_id = self.credit_type
        documents = self.env["document.document"].create(
            {
                "name": f"{name} doc",
                "type": "binary",
                "folder_id": self.root.id,
                "partner_id": partner.id,
                "raw": b"x",
                "document_type_id": self.doc_type.id,
            }
        )
        for values in extra_documents:
            documents |= self.env["document.document"].create(
                dict(
                    values,
                    type="binary",
                    raw=b"x",
                    folder_id=self.root.id,
                    partner_id=partner.id,
                )
            )
        partner.invalidate_recordset()
        self.assertEqual(partner.credit_status, "authorized")
        return partner

    def _overdue_invoice(self, partner, amount):
        invoice = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": partner.id,
                "journal_id": self.journal.id,
                "invoice_date": Date.today() - timedelta(days=90),
                "invoice_date_due": Date.today() - timedelta(days=60),
                "invoice_line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1,
                            "price_unit": amount,
                        }
                    )
                ],
            }
        )
        invoice.action_post()
        return invoice


class TestOverdueIsCheckedLive(CreditScenarioCase):
    def test_overdue_receivable_blocks_credit_terms(self):
        partner = self._compliant_partner("Live Overdue")
        self._overdue_invoice(partner, 5000.0)
        self.assertTrue(
            partner._get_live_overdue_amount(),
            "the enforcement path must see the books as they are now, "
            "not as account_followup last cached them",
        )
        with self.assertRaises(ValidationError):
            partner._check_credit_status(immediate=False)

    def test_overdue_receivable_does_not_freeze_the_stored_status(self):
        partner = self._compliant_partner("Stored Status")
        self._overdue_invoice(partner, 5000.0)
        self.env.flush_all()
        self.env.invalidate_all()
        profile = partner.sudo().credit_profile_id
        self.env.cr.execute(
            "SELECT state FROM credit_profile WHERE id = %s", (profile.id,)
        )
        self.assertEqual(
            self.env.cr.fetchone()[0],
            "active",
            "the stored state tracks the grade and the nightly metrics; a fresh "
            "overdue is a live check",
        )
        self.assertIn("Overdue receivables", partner.credit_type_warning)

    def test_settling_the_debt_unblocks_immediately(self):
        partner = self._compliant_partner("Settled")
        invoice = self._overdue_invoice(partner, 5000.0)
        self.assertTrue(partner._get_live_overdue_amount())
        invoice._reverse_moves([{"date": Date.today()}], cancel=True)
        self.env.flush_all()
        self.assertEqual(
            invoice.amount_residual, 0.0, "the fixture must actually settle the debt"
        )
        self.assertFalse(
            partner._get_live_overdue_amount(),
            "a settled debt must clear the block in the same breath",
        )
        partner._check_credit_status(immediate=False)

    def test_credit_type_warning_is_not_stored(self):
        self.assertFalse(
            self.env["res.partner"]._fields["credit_type_warning"].store,
            "a warning quoting a balance that moves with the calendar "
            "must never be stored",
        )


class TestCreditLimitIsBackedByValidCollateral(CreditScenarioCase):
    def test_expired_collateral_does_not_fund_the_limit(self):
        partner = self._compliant_partner(
            "Expired Collateral",
            extra_documents=[
                {
                    "name": "expired guarantee",
                    "document_type_id": self.collateral_type.id,
                    "collateral_amount": 100000.0,
                    "date_expiration": Date.today() - timedelta(days=5),
                }
            ],
        )
        self.credit_type.rule_ids = [
            Command.create(
                {
                    "name": "collateral",
                    "document_type_id": self.collateral_type.id,
                    "min_quantity": 1,
                }
            )
        ]
        partner.invalidate_recordset()
        self.assertEqual(
            partner.credit_limit,
            0.0,
            "an expired guarantee must not back a single unit of credit",
        )

    def test_valid_collateral_funds_the_limit(self):
        partner = self._compliant_partner(
            "Valid Collateral",
            extra_documents=[
                {
                    "name": "valid guarantee",
                    "document_type_id": self.collateral_type.id,
                    "collateral_amount": 100000.0,
                    "date_expiration": Date.today() + timedelta(days=365),
                }
            ],
        )
        self.credit_type.rule_ids = [
            Command.create(
                {
                    "name": "collateral",
                    "document_type_id": self.collateral_type.id,
                    "min_quantity": 1,
                }
            )
        ]
        partner.invalidate_recordset()
        self.assertEqual(partner.credit_limit, 100000.0)

    def test_no_shipped_credit_condition_grants_unlimited_credit(self):
        for credit_type in self.env["credit.grade"].search([]):
            with self.subTest(credit_type=credit_type.name):
                partner = self.env["res.partner"].create(
                    {
                        "name": f"Shipped {credit_type.name}",
                        "is_company": True,
                        "credit_exception": True,
                        "credit_grade_id": credit_type.id,
                    }
                )
                self.assertEqual(partner.credit_status, "authorized")
                self.assertEqual(partner.credit_limit, 0.0)
                order = self.env["sale.order"].create(
                    {
                        "partner_id": partner.id,
                        "payment_term_id": self.credit_term.id,
                        "line_ids": [
                            Command.create(
                                {"product_id": self.product.id, "product_qty": 1}
                            )
                        ],
                    }
                )
                self.assertTrue(
                    order._is_credit_limit_exceeded(),
                    f"{credit_type.name!r} partners are backed by nothing and "
                    "must not be exempt from the credit limit",
                )


class TestActionConfirmContract(CreditAuthorizationCase, CreditScenarioCase):
    def _exceeding_order(self, partner):
        return self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "payment_term_id": self.credit_term.id,
                "line_ids": [
                    Command.create({"product_id": self.product.id, "product_qty": 50})
                ],
            }
        )

    def test_action_confirm_never_returns_an_action(self):
        partner = self._compliant_partner("Confirm Contract")
        order = self._exceeding_order(partner)
        self.assertTrue(order._is_credit_limit_exceeded())
        with self.assertRaises(RedirectWarning):
            order.action_confirm()
        self.assertEqual(
            order.state,
            "draft",
            "a blocked order must raise, never silently stay in draft",
        )

    def test_action_confirm_returns_bool_when_it_succeeds(self):
        partner = self._compliant_partner("Confirm Ok")
        partner.credit_trusted_amount = 1000000.0
        partner.invalidate_recordset()
        order = self._exceeding_order(partner)
        self.assertFalse(order._is_credit_limit_exceeded())
        self.assertIs(order.action_confirm(), True)

    def test_the_refusal_hands_a_manager_the_wizard(self):
        partner = self._compliant_partner("Confirm Wizard")
        order = self._exceeding_order(partner)
        action = self._credit_authorization_action(order)
        self.assertEqual(
            action["context"]["default_order_ids"], [Command.set(order.ids)]
        )
        self.assertEqual(order.state, "draft")

    def test_wizard_does_not_pre_confirm_the_safe_orders(self):
        partner = self._compliant_partner("Batch")
        partner.credit_trusted_amount = 40000.0
        partner.invalidate_recordset()
        safe = self.env["sale.order"].create(
            {
                "partner_id": partner.id,
                "payment_term_id": self.credit_term.id,
                "line_ids": [
                    Command.create({"product_id": self.product.id, "product_qty": 1})
                ],
            }
        )
        blocked = self._exceeding_order(partner)
        wizard = self._credit_authorization_wizard(safe | blocked)
        self.assertEqual(wizard.order_ids, blocked)
        self.assertEqual(wizard.safe_order_ids, safe)
        self.assertEqual(
            safe.state,
            "draft",
            "cancelling the wizard must not leave half the batch confirmed",
        )


class TestLegalHold(CreditScenarioCase):
    def test_legal_hold_is_the_only_input_to_the_legal_status(self):
        partner = self._compliant_partner("Legal")
        partner.credit_legal_hold = True
        self.assertEqual(partner.credit_status, "legal")
        partner.credit_grade_id = False
        self.assertEqual(
            partner.credit_status,
            "legal",
            "no other change may knock a partner out of legal process",
        )
        partner.credit_legal_hold = False
        self.assertEqual(partner.credit_status, "cash")

    def test_legal_hold_on_a_child_blocks_the_family(self):
        parent = self._compliant_partner("Legal Parent")
        child = self.env["res.partner"].create(
            {"name": "Legal Child", "parent_id": parent.id, "type": "invoice"}
        )
        child.credit_legal_hold = True
        self.assertTrue(parent.credit_legal_hold)
        order = self.env["sale.order"].create(
            {
                "partner_id": child.id,
                "line_ids": [
                    Command.create({"product_id": self.product.id, "product_qty": 1})
                ],
            }
        )
        with self.assertRaises(ValidationError):
            order.action_confirm()
