from datetime import timedelta

from psycopg import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.fields import Date
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestCreditValidation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Test Credit Partner"})

        cls.regular_user = cls.env["res.users"].create(
            {
                "name": "Regular Test User",
                "login": "test_credit_regular",
                "email": "test_credit_regular@example.com",
            }
        )

    def test_legal_blocks_credit_term(self):
        self.partner.write({"credit_legal_hold": True})
        with self.assertRaises(ValidationError):
            self.partner.with_user(self.regular_user)._check_credit_status(
                immediate=False
            )

    def test_legal_blocks_immediate_term(self):
        self.partner.write({"credit_legal_hold": True})
        with self.assertRaises(ValidationError):
            self.partner.with_user(self.regular_user)._check_credit_status(
                immediate=True
            )

    def test_authorized_allows_credit_term(self):
        self.partner.write({"credit_status": "authorized"})
        result = self.partner.with_user(self.regular_user)._check_credit_status(
            immediate=False
        )
        self.assertTrue(result)

    def test_authorized_allows_immediate_term(self):
        self.partner.write({"credit_status": "authorized"})
        result = self.partner.with_user(self.regular_user)._check_credit_status(
            immediate=True
        )
        self.assertTrue(result)

    def test_cash_blocks_credit_term(self):
        self.partner.write({"credit_status": "cash"})
        with self.assertRaises(ValidationError):
            self.partner.with_user(self.regular_user)._check_credit_status(
                immediate=False
            )

    def test_cash_allows_immediate_term(self):
        self.partner.write({"credit_status": "cash"})
        result = self.partner.with_user(self.regular_user)._check_credit_status(
            immediate=True
        )
        self.assertTrue(result)

    def test_review_blocks_credit_term(self):
        self.partner.write({"credit_status": "review"})
        with self.assertRaises(ValidationError):
            self.partner.with_user(self.regular_user)._check_credit_status(
                immediate=False
            )

    def test_review_allows_immediate_term(self):
        self.partner.write({"credit_status": "review"})
        result = self.partner.with_user(self.regular_user)._check_credit_status(
            immediate=True
        )
        self.assertTrue(result)

    def test_toggle_legal_on(self):
        self.partner.write({"credit_status": "authorized"})
        self.partner.action_toggle_legal()
        self.assertEqual(self.partner.credit_status, "legal")

    def test_toggle_legal_off(self):
        self.partner.write({"credit_legal_hold": True})
        self.partner.action_toggle_legal()
        self.assertNotEqual(self.partner.credit_status, "legal")


@tagged("post_install", "-at_install")
class TestCreditException(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "Bypass Test Partner"})
        cls.regular_user = cls.env["res.users"].create(
            {
                "name": "Bypass Regular User",
                "login": "test_bypass_regular",
                "email": "test_bypass_regular@example.com",
            }
        )

    def test_bypass_allows_credit_for_cash_partner(self):
        self.partner.write({"credit_status": "cash", "credit_exception": True})
        result = self.partner.with_user(self.regular_user)._check_credit_status(
            immediate=False
        )
        self.assertTrue(result)

    def test_bypass_allows_credit_for_review_partner(self):
        self.partner.write({"credit_status": "review", "credit_exception": True})
        result = self.partner.with_user(self.regular_user)._check_credit_status(
            immediate=False
        )
        self.assertTrue(result)

    def test_bypass_does_not_override_legal(self):
        self.partner.write({"credit_exception": False})
        self.partner.write({"credit_legal_hold": True})
        with self.assertRaises(ValidationError):
            self.partner.with_user(self.regular_user)._check_credit_status(
                immediate=False
            )

    def test_no_bypass_blocks_credit(self):
        self.partner.write({"credit_status": "cash", "credit_exception": False})
        with self.assertRaises(ValidationError):
            self.partner.with_user(self.regular_user)._check_credit_status(
                immediate=False
            )


@tagged("post_install", "-at_install")
class TestCreditTypeRuleConstraint(TransactionCase):
    def test_min_greater_than_max_raises(self):
        doc_type = self.env["document.type"].create(
            {"name": "Test Type Constraint", "code": "TEST_CONSTR"}
        )
        credit_type = self.env["credit.grade"].create({"name": "Test Credit Type"})
        with self.assertRaises(ValidationError):
            self.env["credit.grade.rule"].create(
                {
                    "name": "Bad Rule",
                    "document_type_id": doc_type.id,
                    "grade_id": credit_type.id,
                    "min_quantity": 5,
                    "max_quantity": 2,
                }
            )


@tagged("post_install", "-at_install")
class TestDocumentExpiration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder = cls.env["document.document"].create(
            {
                "name": "Test Folder",
                "type": "folder",
            }
        )
        cls.doc_type = cls.env["document.type"].create(
            {"name": "Expiring Credit Type", "code": "CREDIT_EXPIRING"}
        )

    def test_expired_document(self):
        doc = self.env["document.document"].create(
            {
                "name": "Expired Doc",
                "folder_id": self.folder.id,
                "document_type_id": self.doc_type.id,
                "date_expiration": Date.today() - timedelta(days=1),
            }
        )
        self.assertEqual(doc.expiration_state, "expired")

    def test_valid_document_not_expired(self):
        doc = self.env["document.document"].create(
            {
                "name": "Valid Doc",
                "folder_id": self.folder.id,
                "document_type_id": self.doc_type.id,
                "date_expiration": Date.today() + timedelta(days=30),
            }
        )
        self.assertNotEqual(doc.expiration_state, "expired")


@tagged("post_install", "-at_install")
class TestCreditStatusComputation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder = cls.env["document.document"].create(
            {
                "name": "Status Folder",
                "type": "folder",
            }
        )
        # A credit document is one filed under the company's credit folder.
        cls.env.company.credit_folder_id = cls.folder
        cls.doc_type = cls.env["document.type"].create(
            {"name": "Status Type", "code": "TEST_STATUS"}
        )
        cls.credit_type = cls.env["credit.grade"].create(
            {
                "name": "Status Credit Type",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "Status Rule",
                            "document_type_id": cls.doc_type.id,
                            "min_quantity": 1,
                        }
                    )
                ],
            }
        )

    def test_no_profile_gives_no_status(self):
        partner = self.env["res.partner"].create({"name": "No Credit Type Partner"})
        self.assertFalse(partner.credit_status)

    def test_complete_credit_type_gives_authorized(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Authorized Partner",
                "credit_grade_id": self.credit_type.id,
            }
        )
        doc = self.env["document.document"].create(
            {
                "name": "Compliant Doc",
                "folder_id": self.folder.id,
                "partner_id": partner.id,
                "document_type_id": self.doc_type.id,
            }
        )
        partner.write({"credit_document_ids": [Command.link(doc.id)]})
        self.assertEqual(partner.credit_status, "authorized")

    def test_credit_type_with_warning_gives_review(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Review Partner",
                "credit_grade_id": self.credit_type.id,
            }
        )
        self.assertEqual(partner.credit_status, "review")

    def test_legal_status_preserved(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Legal Partner",
                "credit_grade_id": self.credit_type.id,
            }
        )
        partner.write({"credit_legal_hold": True})
        partner.invalidate_recordset(["credit_status"])
        partner._compute_credit_status()
        self.assertEqual(partner.credit_status, "legal")


@tagged("post_install", "-at_install")
class TestCreditTypeWarning(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder = cls.env["document.document"].create(
            {
                "name": "Warning Folder",
                "type": "folder",
            }
        )
        # A credit document is one filed under the company's credit folder.
        cls.env.company.credit_folder_id = cls.folder
        cls.doc_type = cls.env["document.type"].create(
            {
                "name": "Warning Type",
                "code": "TEST_WARNING",
                "has_expiration": True,
            }
        )
        cls.credit_type = cls.env["credit.grade"].create(
            {
                "name": "Warning Credit Type",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "Warning Rule",
                            "document_type_id": cls.doc_type.id,
                            "min_quantity": 1,
                        }
                    )
                ],
            }
        )

    def test_no_credit_type_no_warning(self):
        partner = self.env["res.partner"].create({"name": "No Credit Type Warning"})
        self.assertFalse(partner.credit_type_warning)

    def test_overdue_summary_in_credit_type_warning(self):
        partner = self.env["res.partner"].create(
            {"name": "Overdue Warning", "credit_grade_id": self.credit_type.id}
        )
        self.assertIn("Missing", partner.credit_type_warning)
        summary = partner._get_overdue_receivable_summary()
        if summary:
            self.assertIn("Overdue receivables", partner.credit_type_warning)

    def test_bypass_no_credit_type_no_overdue_clean(self):
        partner = self.env["res.partner"].create(
            {"name": "Bypass Clean", "credit_exception": True}
        )
        self.assertFalse(partner.credit_type_warning)

    def test_bypass_no_credit_type_with_overdue_shows_warning(self):
        partner = self.env["res.partner"].create(
            {"name": "Bypass Overdue", "credit_exception": True}
        )
        self.assertFalse(partner.credit_type_warning)
        self.assertEqual(partner.credit_grade_id.kind, "entry")
        self.assertTrue(partner.sudo().credit_exception)

    def test_no_documents_warning(self):
        partner = self.env["res.partner"].create(
            {
                "name": "No Docs Warning",
                "credit_grade_id": self.credit_type.id,
            }
        )
        self.assertIn("Missing", partner.credit_type_warning)
        self.assertFalse(partner.credit_document_compliant)

    def test_rule_free_credit_type_is_compliant_without_documents(self):
        rule_free = self.env["credit.grade"].create({"name": "Rule Free"})
        partner = self.env["res.partner"].create(
            {"name": "Rule Free Partner", "credit_grade_id": rule_free.id}
        )
        self.assertFalse(partner.credit_document_ids)
        self.assertTrue(partner.credit_document_compliant)
        self.assertFalse(partner.credit_type_warning)
        self.assertEqual(partner.credit_status, "authorized")

    def test_missing_document_warning(self):
        other_type = self.env["document.type"].create(
            {"name": "Other Type", "code": "TEST_OTHER"}
        )
        partner = self.env["res.partner"].create(
            {
                "name": "Missing Doc Warning",
                "credit_grade_id": self.credit_type.id,
            }
        )
        doc = self.env["document.document"].create(
            {
                "name": "Wrong Type Doc",
                "folder_id": self.folder.id,
                "partner_id": partner.id,
                "document_type_id": other_type.id,
            }
        )
        partner.write({"credit_document_ids": [Command.link(doc.id)]})
        self.assertIn("Missing", partner.credit_type_warning)

    def test_expired_document_warning(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Expired Doc Warning",
                "credit_grade_id": self.credit_type.id,
            }
        )
        doc = self.env["document.document"].create(
            {
                "name": "Expired Warning Doc",
                "folder_id": self.folder.id,
                "partner_id": partner.id,
                "document_type_id": self.doc_type.id,
                "date_expiration": Date.today() - timedelta(days=1),
            }
        )
        partner.write({"credit_document_ids": [Command.link(doc.id)]})
        self.assertIn("Expired", partner.credit_type_warning)

    def test_extra_document_outside_rules_ignored(self):
        extra_type = self.env["document.type"].create(
            {"name": "Extra Type", "code": "TEST_EXTRA", "has_expiration": True}
        )
        partner = self.env["res.partner"].create(
            {
                "name": "Extra Doc Partner",
                "credit_grade_id": self.credit_type.id,
            }
        )
        valid_doc = self.env["document.document"].create(
            {
                "name": "Valid Required Doc",
                "folder_id": self.folder.id,
                "partner_id": partner.id,
                "document_type_id": self.doc_type.id,
                "date_expiration": Date.today() + timedelta(days=365),
            }
        )
        extra_doc = self.env["document.document"].create(
            {
                "name": "Extra Expired Doc",
                "folder_id": self.folder.id,
                "partner_id": partner.id,
                "document_type_id": extra_type.id,
                "date_expiration": Date.today() - timedelta(days=1),
            }
        )
        partner.write(
            {
                "credit_document_ids": [
                    Command.link(valid_doc.id),
                    Command.link(extra_doc.id),
                ],
            }
        )
        self.assertFalse(
            partner.credit_type_warning,
            "Extra expired document outside credit type rules should not trigger warning",
        )
        self.assertEqual(partner.credit_status, "authorized")


@tagged("post_install", "-at_install")
class TestCreditLimit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder = cls.env["document.document"].create(
            {
                "name": "Limit Folder",
                "type": "folder",
            }
        )
        # A credit document is one filed under the company's credit folder.
        cls.env.company.credit_folder_id = cls.folder
        cls.doc_type = cls.env["document.type"].create(
            {
                "name": "Limit Type",
                "code": "TEST_LIMIT",
                "has_collateral": True,
            }
        )
        cls.credit_type = cls.env["credit.grade"].create(
            {
                "name": "Limit Credit Type",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "Limit Rule",
                            "document_type_id": cls.doc_type.id,
                            "min_quantity": 1,
                        }
                    )
                ],
            }
        )

    def test_credit_limit_from_collateral(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Collateral Partner",
                "credit_grade_id": self.credit_type.id,
            }
        )
        doc = self.env["document.document"].create(
            {
                "name": "Collateral Doc",
                "folder_id": self.folder.id,
                "partner_id": partner.id,
                "document_type_id": self.doc_type.id,
                "collateral_amount": 10000.0,
            }
        )
        partner.write(
            {
                "credit_document_ids": [Command.link(doc.id)],
                "credit_trusted_amount": 5000.0,
            }
        )
        self.assertEqual(partner.credit_limit, 15000.0)

    def test_credit_limit_no_credit_type(self):
        company_limit = (
            self.env["res.partner"]
            ._fields["credit_limit"]
            .get_company_dependent_fallback(self.env["res.partner"])
        )
        partner = self.env["res.partner"].create({"name": "No Credit Type Limit"})
        self.assertEqual(partner.credit_limit, company_limit)


@tagged("post_install", "-at_install")
class TestOverdueReceivables(TransactionCase):
    def test_no_overdue_receivable(self):
        partner = self.env["res.partner"].create({"name": "Overdue Partner"})
        self.assertFalse(partner._get_overdue_receivable_summary())


@tagged("post_install", "-at_install")
class TestSaleOrderValidation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "SO Test Partner"})
        cls.credit_term = cls.env["account.payment.term"].create(
            {
                "name": "SO 30 Days",
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
        cls.regular_user = cls.env["res.users"].create(
            {
                "name": "SO Regular User",
                "login": "test_so_regular",
                "email": "test_so_regular@example.com",
                "group_ids": [
                    Command.link(cls.env.ref("sale.group_sale_salesman").id),
                ],
            }
        )

    def _create_sale_order(self, payment_term=None):
        product = self.env["product.product"].create(
            {"name": "Test Product", "list_price": 100.0}
        )
        if payment_term is None:
            payment_term = self.credit_term
        return (
            self.env["sale.order"]
            .with_user(self.regular_user)
            .create(
                {
                    "partner_id": self.partner.id,
                    "payment_term_id": payment_term.id,
                    "line_ids": [
                        Command.create(
                            {
                                "product_id": product.id,
                                "product_qty": 1.0,
                            }
                        )
                    ],
                }
            )
        )

    def test_check_confirm_credit_status_blocks_legal(self):
        self.partner.write({"credit_legal_hold": True})
        order = self._create_sale_order()
        with self.assertRaises(ValidationError):
            order._check_confirm_credit_status()

    def test_check_confirm_credit_status_allows_authorized(self):
        self.partner.write({"credit_status": "authorized"})
        order = self._create_sale_order()
        order._check_confirm_credit_status()

    def test_cash_partner_order_without_payment_term_is_immediate(self):
        self.partner.credit_status = "cash"
        order = self._create_sale_order(self.env["account.payment.term"])
        self.assertTrue(order._is_immediate_payment())
        order._check_confirm_credit_status()

    def test_cash_partner_order_with_credit_term_is_blocked(self):
        self.partner.credit_status = "cash"
        order = self._create_sale_order()
        self.assertFalse(order._is_immediate_payment())
        with self.assertRaises(ValidationError):
            order._check_confirm_credit_status()

    def test_check_confirm_credit_status_in_registry(self):
        order = self._create_sale_order()
        methods = order._get_confirm_validation_methods()
        self.assertIn("_check_confirm_credit_status", methods)


@tagged("post_install", "-at_install")
class TestInvoiceValidation(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create({"name": "INV Test Partner"})
        cls.credit_term = cls.env["account.payment.term"].create(
            {
                "name": "INV 30 Days",
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
        cls.regular_user = cls.env["res.users"].create(
            {
                "name": "INV Regular User",
                "login": "test_inv_regular",
                "email": "test_inv_regular@example.com",
                "group_ids": [
                    Command.link(cls.env.ref("account.group_account_invoice").id),
                ],
            }
        )

    def _create_invoice(self, **values):
        return (
            self.env["account.move"]
            .with_user(self.regular_user)
            .create(
                {
                    "move_type": "out_invoice",
                    "partner_id": self.partner.id,
                    "invoice_date": Date.today(),
                    "invoice_line_ids": [
                        Command.create(
                            {"name": "Credit line", "quantity": 1, "price_unit": 100.0}
                        )
                    ],
                    **values,
                }
            )
        )

    def test_invoice_post_blocked_for_legal(self):
        self.partner.write({"credit_legal_hold": True})
        invoice = self._create_invoice()
        with self.assertRaises(ValidationError):
            invoice.action_post()

    def test_invoice_post_allowed_for_authorized(self):
        self.partner.write({"credit_status": "authorized"})
        invoice = self._create_invoice(invoice_payment_term_id=self.credit_term.id)
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")

    def test_cash_invoice_without_payment_term_due_on_invoice_date_posts(self):
        self.partner.credit_status = "cash"
        invoice = self._create_invoice()
        self.assertTrue(invoice._is_immediate_payment())
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")

    def test_cash_invoice_without_payment_term_due_later_is_blocked(self):
        self.partner.credit_status = "cash"
        invoice = self._create_invoice(
            invoice_date_due=Date.today() + timedelta(days=30)
        )
        self.assertFalse(invoice._is_immediate_payment())
        with self.assertRaises(ValidationError):
            invoice.action_post()

    def test_cash_invoice_with_credit_term_is_blocked(self):
        self.partner.credit_status = "cash"
        invoice = self._create_invoice(invoice_payment_term_id=self.credit_term.id)
        self.assertFalse(invoice._is_immediate_payment())
        with self.assertRaises(ValidationError):
            invoice.action_post()


@tagged("post_install", "-at_install")
class TestComplianceCreditIntegration(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder = cls.env["document.document"].create(
            {"name": "Integration Folder", "type": "folder"}
        )
        # A credit document is one filed under the company's credit folder.
        cls.env.company.credit_folder_id = cls.folder
        cls.doc_type = cls.env["document.type"].create(
            {
                "name": "Integration Type",
                "code": "TEST_INTEG",
                "has_expiration": True,
                "has_amount": True,
            }
        )
        cls.credit_type = cls.env["credit.grade"].create(
            {
                "name": "Integration Credit Type",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "Integration Rule",
                            "document_type_id": cls.doc_type.id,
                            "min_quantity": 1,
                        }
                    )
                ],
            }
        )

    def test_expired_doc_triggers_review(self):
        partner = self.env["res.partner"].create(
            {"name": "Expired Integration", "credit_grade_id": self.credit_type.id}
        )
        doc = self.env["document.document"].create(
            {
                "name": "Expired Integ Doc",
                "folder_id": self.folder.id,
                "partner_id": partner.id,
                "document_type_id": self.doc_type.id,
                "date_expiration": Date.today() - timedelta(days=1),
                "amount": 1000.0,
            }
        )
        partner.write({"credit_document_ids": [Command.link(doc.id)]})
        self.assertEqual(doc.expiration_state, "expired")
        self.assertIn("Expired", partner.credit_type_warning)
        self.assertEqual(partner.credit_status, "review")

    def test_valid_doc_gives_authorized(self):
        partner = self.env["res.partner"].create(
            {"name": "Valid Integration", "credit_grade_id": self.credit_type.id}
        )
        doc = self.env["document.document"].create(
            {
                "name": "Valid Integ Doc",
                "folder_id": self.folder.id,
                "partner_id": partner.id,
                "document_type_id": self.doc_type.id,
                "date_expiration": Date.today() + timedelta(days=90),
                "amount": 5000.0,
            }
        )
        partner.write({"credit_document_ids": [Command.link(doc.id)]})
        self.assertFalse(partner.credit_type_warning)
        self.assertEqual(partner.credit_status, "authorized")

    def test_credit_exception_bypasses_expired(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Exception Integration",
                "credit_grade_id": self.credit_type.id,
                "credit_exception": True,
            }
        )
        doc = self.env["document.document"].create(
            {
                "name": "Expired Exception Doc",
                "folder_id": self.folder.id,
                "partner_id": partner.id,
                "document_type_id": self.doc_type.id,
                "date_expiration": Date.today() - timedelta(days=30),
            }
        )
        partner.write({"credit_document_ids": [Command.link(doc.id)]})
        self.assertFalse(partner.credit_type_warning)
        self.assertEqual(partner.credit_status, "authorized")


@tagged("post_install", "-at_install")
class TestDocumentTypeFieldVisibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.folder = cls.env["document.document"].create(
            {"name": "Visibility Folder", "type": "folder"}
        )

    def test_missing_amount_issue(self):
        doc_type = self.env["document.type"].create(
            {"name": "Amount Type", "code": "TEST_AMT", "has_amount": True}
        )
        doc = self.env["document.document"].create(
            {
                "name": "No Amount Doc",
                "folder_id": self.folder.id,
                "document_type_id": doc_type.id,
            }
        )
        issues = doc._get_compliance_issues()
        self.assertEqual(len(issues), 1)
        self.assertIn("amount", issues[0].lower())

    def test_missing_collateral_issue(self):
        doc_type = self.env["document.type"].create(
            {"name": "Collateral Type", "code": "TEST_COLL", "has_collateral": True}
        )
        doc = self.env["document.document"].create(
            {
                "name": "No Collateral Doc",
                "folder_id": self.folder.id,
                "document_type_id": doc_type.id,
            }
        )
        issues = doc._get_compliance_issues()
        self.assertEqual(len(issues), 1)
        self.assertIn("collateral", issues[0].lower())

    def test_expired_issue(self):
        doc_type = self.env["document.type"].create(
            {"name": "Expiration Type", "code": "TEST_EXP", "has_expiration": True}
        )
        doc = self.env["document.document"].create(
            {
                "name": "Expired Vis Doc",
                "folder_id": self.folder.id,
                "document_type_id": doc_type.id,
                "date_expiration": Date.today() - timedelta(days=1),
            }
        )
        issues = doc._get_compliance_issues()
        self.assertEqual(len(issues), 1)
        self.assertIn("expired", issues[0].lower())

    def test_no_issues_when_compliant(self):
        doc_type = self.env["document.type"].create(
            {
                "name": "Full Type",
                "code": "TEST_FULL",
                "has_expiration": True,
                "has_amount": True,
                "has_collateral": True,
            }
        )
        doc = self.env["document.document"].create(
            {
                "name": "Full Compliant Doc",
                "folder_id": self.folder.id,
                "document_type_id": doc_type.id,
                "date_expiration": Date.today() + timedelta(days=90),
                "amount": 5000.0,
                "collateral_amount": 3000.0,
            }
        )
        issues = doc._get_compliance_issues()
        self.assertEqual(len(issues), 0)

    def test_no_type_no_issues(self):
        doc = self.env["document.document"].create(
            {
                "name": "No Type Doc",
                "folder_id": self.folder.id,
            }
        )
        issues = doc._get_compliance_issues()
        self.assertEqual(len(issues), 0)


@tagged("post_install", "-at_install")
class TestCreditTypeRuleUniqueness(TransactionCase):
    def test_credit_type_rule_uniqueness(self):
        credit_type = self.env["credit.grade"].create({"name": "Uniq Test Type"})
        doc_type = self.env["document.type"].create(
            {"name": "Uniq Test Doc Type", "code": "TEST_UNIQ"}
        )
        self.env["credit.grade.rule"].create(
            {
                "name": "Uniq Rule 1",
                "grade_id": credit_type.id,
                "document_type_id": doc_type.id,
                "is_guarantor": False,
                "min_quantity": 1,
            }
        )
        with self.assertRaises(IntegrityError), mute_logger("odoo.db"):
            self.env["credit.grade.rule"].create(
                {
                    "name": "Uniq Rule 1 dup",
                    "grade_id": credit_type.id,
                    "document_type_id": doc_type.id,
                    "is_guarantor": False,
                    "min_quantity": 2,
                }
            )


@tagged("post_install", "-at_install")
class TestCanonicalDocumentTypesGlobal(TransactionCase):
    CANONICAL_XMLIDS = (
        "account_credit.doc_type_id_document",
        "account_credit.doc_type_contract",
        "account_credit.doc_type_promissory_note",
        "account_credit.doc_type_warranty",
        "account_credit.doc_type_credit_application",
        "account_credit.doc_type_proof_of_address",
        "account_credit.doc_type_authorized_signatures",
    )

    def _canonical_types(self):
        types = self.env["document.type"]
        for xmlid in self.CANONICAL_XMLIDS:
            types |= self.env.ref(xmlid)
        return types

    def test_canonical_doc_types_are_global(self):
        types = self._canonical_types()
        self.assertEqual(len(types), 7, f"found {types.mapped('code')}")
        for dt in types:
            self.assertFalse(
                dt.company_id,
                f"Canonical type {dt.code} has company_id="
                f"{dt.company_id.name!r}; must be False to remain visible "
                f"across all companies via document_type_comp_rule",
            )

    def test_canonical_doc_types_visible_from_other_company(self):
        canonical = self._canonical_types()
        other_company = self.env["res.company"].create({"name": "Test Co Multi"})
        other_user = self.env["res.users"].create(
            {
                "name": "Multi Co User",
                "login": "test_multi_co_user@test.com",
                "company_ids": [Command.set([other_company.id])],
                "company_id": other_company.id,
                "group_ids": [Command.link(self.env.ref("base.group_user").id)],
            }
        )
        doc_type_model = (
            self.env["document.type"].with_user(other_user).with_company(other_company)
        )
        visible = doc_type_model.search([("id", "in", canonical.ids)])
        missing = canonical - visible
        self.assertFalse(
            missing,
            f"Canonical types not visible to user in {other_company.name!r}: "
            f"{sorted(missing.mapped('code'))}. document_type_comp_rule is "
            f"filtering records that should be global (company_id=False).",
        )


@tagged("post_install", "-at_install")
class TestActionOpenDocument(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.doc_type = cls.env["document.type"].create(
            {"name": "Action Test Type", "code": "ACTION_VIEW_TEST"}
        )
        cls.document = cls.env["document.document"].create(
            {
                "name": "Action Open Test Doc",
                "document_type_id": cls.doc_type.id,
            }
        )

    def test_action_view_document_returns_act_url(self):
        action = self.document.action_view_document()
        self.assertEqual(
            action["type"],
            "ir.actions.act_url",
            "action_view_document must return act_url so the browser "
            "handles the response (binary served by the controller), "
            "not act_window which would render a metadata form without "
            "the file preview",
        )
        self.assertEqual(action["target"], "new")

    def test_action_view_document_uses_documents_content_route(self):
        action = self.document.action_view_document()
        url = action["url"]
        self.assertIn(
            "/documents/content/",
            url,
            f"URL must use the /documents/content/<token> controller "
            f"(serves binary directly); got: {url}",
        )
        self.assertNotIn(
            "/odoo/documents/",
            url,
            f"URL must NOT use /odoo/documents/<token> (the SPA "
            f"deep-link causes cold-boot race in new tabs); got: {url}",
        )

    def test_action_view_document_disables_forced_download(self):
        action = self.document.action_view_document()
        self.assertIn(
            "download=false",
            action["url"],
            f"URL must include 'download=false' so the controller "
            f"sends Content-Disposition: inline; got: {action['url']}",
        )


@tagged("post_install", "-at_install")
class TestCreditDocumentVisibility(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        doc_model = cls.env["document.document"]
        cls.folder = doc_model.create(
            {"name": "T21990 Credit Folder", "type": "folder"}
        )
        cls.doc_a = doc_model.create(
            {"name": "doc_a", "folder_id": cls.folder.id, "type": "binary"}
        )
        cls.doc_b = doc_model.create(
            {"name": "doc_b", "folder_id": cls.folder.id, "type": "binary"}
        )
        cls.doc_c = doc_model.create(
            {"name": "doc_c", "folder_id": cls.folder.id, "type": "binary"}
        )
        cls.subfolder = doc_model.create(
            {
                "name": "T21990 Sub",
                "type": "folder",
                "folder_id": cls.folder.id,
            }
        )
        cls.doc_sub = doc_model.create(
            {"name": "doc_sub", "folder_id": cls.subfolder.id, "type": "binary"}
        )
        cls.other_folder = doc_model.create(
            {"name": "T21990 Outside", "type": "folder"}
        )
        (
            cls.folder
            + cls.doc_a
            + cls.doc_b
            + cls.doc_c
            + cls.subfolder
            + cls.doc_sub
            + cls.other_folder
        ).write({"access_internal": "none", "access_via_link": "none"})
        cls.env.company.credit_folder_id = cls.folder

        ref = cls.env.ref
        cls.user_plain = cls.env["res.users"].create(
            {
                "name": "T21990 Plain",
                "login": "t21990_plain",
                "group_ids": [Command.link(ref("base.group_user").id)],
            }
        )
        cls.user_credit_view = cls.env["res.users"].create(
            {
                "name": "T21990 Readonly",
                "login": "t21990_credit_view",
                "group_ids": [
                    Command.link(ref("account_credit.group_credit_readonly").id),
                ],
            }
        )
        cls.user_credit_edit = cls.env["res.users"].create(
            {
                "name": "T21990 Editor",
                "login": "t21990_credit_edit",
                "group_ids": [
                    Command.link(ref("account_credit.group_credit_user").id),
                ],
            }
        )
        cls.user_credit_admin = cls.env["res.users"].create(
            {
                "name": "T21990 Admin",
                "login": "t21990_credit_admin",
                "group_ids": [
                    Command.link(ref("account_credit.group_credit_manager").id),
                ],
            }
        )

    def test_credit_readonly_sees_folder_in_documents_app(self):
        doc_model = self.env["document.document"]
        prefix = self.folder.parent_path + "%"
        docs = doc_model.with_user(self.user_credit_view).search(
            [("parent_path", "=like", prefix)]
        )
        self.assertEqual(
            len(docs),
            6,
            f"Expected 6 records (root + 5 children); got {len(docs)}",
        )
        self.assertIn(self.folder, docs, "Root folder must appear in tree search")
        self.assertEqual(
            self.folder.with_user(self.user_credit_view).user_permission,
            "view",
            "Folder root must report user_permission='view' for readonly user",
        )

    def test_credit_user_can_create_and_edit_docs(self):
        doc_model = self.env["document.document"]
        self.assertEqual(
            self.folder.with_user(self.user_credit_edit).user_permission,
            "edit",
        )
        new_doc = (
            doc_model.with_user(self.user_credit_edit)
            .with_company(self.env.company)
            .create(
                {
                    "name": "t21990_new",
                    "folder_id": self.folder.id,
                    "type": "binary",
                }
            )
        )
        self.assertTrue(new_doc.id, "credit_user must be able to create docs")
        self.doc_a.with_user(self.user_credit_edit).write({"name": "renamed"})
        self.assertEqual(self.doc_a.name, "renamed")

    def test_credit_user_cannot_create_outside_credit_tree(self):
        doc_model = self.env["document.document"]
        with self.assertRaises(AccessError):
            doc_model.with_user(self.user_credit_edit).create(
                {
                    "name": "t21990_outside",
                    "folder_id": self.other_folder.id,
                    "type": "binary",
                }
            )

    def test_non_credit_user_sees_no_docs(self):
        doc_model = self.env["document.document"]
        prefix = self.folder.parent_path + "%"
        docs = doc_model.with_user(self.user_plain).search(
            [("parent_path", "=like", prefix)]
        )
        self.assertEqual(len(docs), 0)

    def test_credit_manager_inherits_all(self):
        self.assertTrue(
            self.user_credit_admin.has_group("account_credit.group_credit_user")
        )
        self.assertTrue(
            self.user_credit_admin.has_group("account_credit.group_credit_readonly")
        )

    def test_credit_readonly_cannot_unlink(self):
        with self.assertRaises(AccessError):
            self.doc_a.with_user(self.user_credit_view).unlink()

    def test_credit_edit_users_can_unlink_subfolder_but_not_root(self):
        for user in (self.user_credit_edit, self.user_credit_admin):
            sub = self.env["document.document"].create(
                {
                    "name": f"sub_{user.login}",
                    "type": "folder",
                    "folder_id": self.folder.id,
                }
            )
            sub.with_user(user).unlink()
            with self.assertRaises(
                AccessError, msg=f"{user.login} should not unlink the root"
            ):
                self.folder.with_user(user).unlink()

    def test_multicompany_no_op_without_folder_configured(self):
        doc_model = self.env["document.document"]
        company_b = self.env["res.company"].create({"name": "T21990 B"})
        user_b = self.env["res.users"].create(
            {
                "name": "T21990 B-only",
                "login": "t21990_company_b",
                "company_id": company_b.id,
                "company_ids": [Command.link(company_b.id)],
                "group_ids": [
                    Command.link(
                        self.env.ref("account_credit.group_credit_readonly").id
                    ),
                ],
            }
        )
        prefix = self.folder.parent_path + "%"
        docs = (
            doc_model.with_user(user_b)
            .with_context(allowed_company_ids=[company_b.id])
            .search([("parent_path", "=like", prefix)])
        )
        self.assertEqual(
            len(docs),
            0,
            "a grant limited to a company reaches only who holds the group there",
        )

    def test_the_credit_groups_are_two_grants_that_follow_the_folder(self):
        ref = self.env.ref
        readonly = ref("account_credit.group_credit_readonly")
        user = ref("account_credit.group_credit_user")
        Access = self.env["document.access"]
        folders = self.folder | self.other_folder

        def grants():
            return {
                (grant.document_id, grant.group_id, grant.role, grant.company_id)
                for grant in Access.search(
                    [
                        ("cause_ref", "=", "credit.config"),
                        ("document_id", "in", folders.ids),
                    ]
                )
            }

        company = self.env.company
        self.assertEqual(
            grants(),
            {
                (self.folder, readonly, "view", company),
                (self.folder, user, "edit", company),
            },
        )
        self.env.company.credit_folder_id = self.other_folder
        self.assertEqual(
            grants(),
            {
                (self.other_folder, readonly, "view", company),
                (self.other_folder, user, "edit", company),
            },
            "the grants move with the configured folder",
        )
        self.assertEqual(
            self.doc_a.with_user(self.user_credit_view).user_permission, "none"
        )

    def test_search_user_permission_passes_through_unsupported_operators(self):
        doc_model = self.env["document.document"].with_user(self.user_credit_edit)
        doc_model.search([("user_permission", "=", "edit")], limit=1)
        doc_model.search([("user_permission", "!=", "none")], limit=1)

    def test_disabled_company_not_elevated(self):
        doc_model = self.env["document.document"]
        company_b = self.env["res.company"].create({"name": "T21990 disable"})
        folder_b = doc_model.create(
            {
                "name": "T21990 folder B",
                "type": "folder",
                "company_id": company_b.id,
            }
        )
        doc_b = doc_model.create(
            {
                "name": "doc_in_b",
                "type": "binary",
                "folder_id": folder_b.id,
                "company_id": company_b.id,
                "access_internal": "none",
                "access_via_link": "none",
            }
        )
        company_b.credit_folder_id = folder_b
        user = self.env["res.users"].create(
            {
                "name": "T21990 dual",
                "login": "t21990_dual_company",
                "company_id": self.env.company.id,
                "company_ids": [
                    Command.set([self.env.company.id, company_b.id]),
                ],
                "group_ids": [
                    Command.link(
                        self.env.ref("account_credit.group_credit_readonly").id
                    ),
                ],
            }
        )
        docs = (
            doc_model.with_user(user)
            .with_context(allowed_company_ids=[self.env.company.id])
            .search([("id", "=", doc_b.id)])
        )
        self.assertEqual(
            len(docs),
            0,
            "Docs in a disabled-company folder must not be elevated",
        )
        perm = (
            doc_b.with_user(user)
            .with_context(allowed_company_ids=[self.env.company.id])
            .user_permission
        )
        self.assertEqual(perm, "none")

    def test_credit_readonly_sees_partner_credit_documents(self):
        partner = self.env["res.partner"].create({"name": "T21990 Partner"})
        self.doc_a.partner_id = partner
        partner.credit_document_ids = [(4, self.doc_a.id)]
        docs = partner.with_user(self.user_credit_view).credit_document_ids
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs.name, "doc_a")


@tagged("post_install", "-at_install")
class TestCreditDocumentFile(TransactionCase):
    """A partner's credit file is the documents that name it under the credit folder.

    There is no folder per partner and no link table: which partner a document
    belongs to is its ``partner_id``, and being in the file is being filed
    under the company's credit folder. Filing one recomputes what depends on
    the file without touching the partner itself.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        doc_model = cls.env["document.document"]
        cls.root = doc_model.create({"name": "File Test Root", "type": "folder"})
        cls.env.company.credit_folder_id = cls.root
        cls.subfolder = doc_model.create(
            {"name": "File Test Subfolder", "type": "folder", "folder_id": cls.root.id}
        )
        cls.elsewhere = doc_model.create({"name": "Not Credit", "type": "folder"})
        cls.partner = cls.env["res.partner"].create({"name": "File Test Partner"})

    def _file(self, name, folder, **vals):
        return self.env["document.document"].create(
            {
                "name": name,
                "type": "binary",
                "folder_id": folder.id,
                "partner_id": self.partner.id,
                **vals,
            }
        )

    def test_filing_a_document_does_not_bump_partner_write_date(self):
        self.env.cr.execute(
            "SELECT write_date FROM res_partner WHERE id = %s", (self.partner.id,)
        )
        write_date_before = self.env.cr.fetchone()[0]
        doc = self._file("Filed Doc", self.subfolder)
        self.assertIn(doc, self.partner.credit_document_ids)
        self.env.cr.execute(
            "SELECT write_date FROM res_partner WHERE id = %s", (self.partner.id,)
        )
        self.assertEqual(self.env.cr.fetchone()[0], write_date_before)

    def test_a_document_outside_the_credit_folder_is_not_in_the_file(self):
        outside = self._file("Elsewhere Doc", self.elsewhere)
        self.assertNotIn(outside, self.partner.credit_document_ids)
        outside.folder_id = self.subfolder
        self.assertIn(outside, self.partner.credit_document_ids)
        outside.folder_id = self.elsewhere
        self.assertNotIn(outside, self.partner.credit_document_ids)

    def test_filing_collateral_recomputes_credit_limit(self):
        doc_type = self.env["document.type"].create(
            {
                "name": "File Collateral Type",
                "code": "FILE_COLL",
                "has_collateral": True,
            }
        )
        self.partner.credit_grade_id = self.env["credit.grade"].create(
            {
                "name": "File Collateral Condition",
                "rule_ids": [
                    Command.create(
                        {"name": "collateral", "document_type_id": doc_type.id}
                    )
                ],
            }
        )
        self.partner.invalidate_recordset(["credit_limit"])
        limit_before = self.partner.credit_limit
        self._file(
            "Collateral Doc",
            self.subfolder,
            document_type_id=doc_type.id,
            collateral_amount=1234.0,
        )
        self.partner.invalidate_recordset(["credit_limit"])
        self.assertEqual(self.partner.credit_limit, limit_before + 1234.0)

    def test_collateral_outside_the_rules_does_not_fund_the_limit(self):
        unrequested = self.env["document.type"].create(
            {
                "name": "Unrequested Collateral",
                "code": "UNREQ_COLL",
                "has_collateral": True,
            }
        )
        self.partner.credit_grade_id = self.env["credit.grade"].create(
            {"name": "Asks For Nothing Collateral"}
        )
        self.partner.invalidate_recordset(["credit_limit"])
        limit_before = self.partner.credit_limit
        self._file(
            "Unrequested Collateral Doc",
            self.subfolder,
            document_type_id=unrequested.id,
            collateral_amount=999_999.0,
        )
        self.partner.invalidate_recordset(["credit_limit"])
        self.assertEqual(
            self.partner.credit_limit,
            limit_before,
            "collateral the credit condition never asked for must not raise the limit",
        )
