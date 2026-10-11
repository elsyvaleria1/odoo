from odoo import Command
from odoo.exceptions import AccessError, RedirectWarning, ValidationError
from odoo.tests.common import TransactionCase, tagged

from .common import CreditAuthorizationCase


@tagged("post_install", "-at_install")
class TestCreditAuditR2(CreditAuthorizationCase, TransactionCase):
    """Regression cover for the round-2 audit fixes (parent task 30598).

    Every test below failed on the tree these fixes landed on.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if "so_validation_level" in cls.env["res.company"]._fields:
            cls.env.company.write({"so_validation_level": "none"})
        cls.company_a = cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "Audit R2 Company B"})
        if "so_validation_level" in cls.env["res.company"]._fields:
            cls.company_b.write({"so_validation_level": "none"})

        cls.credit_manager = cls._mkuser(
            "audit_r2_credit_manager",
            (
                "sale.group_sale_salesman",
                "base.group_partner_manager",
                "account_credit.group_credit_manager",
            ),
            both_companies=True,
        )
        cls.partner_manager = cls._mkuser(
            "audit_r2_partner_manager",
            ("base.group_user", "base.group_partner_manager"),
        )
        cls.credit_viewer = cls._mkuser(
            "audit_r2_credit_viewer",
            (
                "base.group_user",
                "base.group_partner_manager",
                "account_credit.group_credit_readonly",
            ),
        )

        cls.unconditional = cls.env["credit.grade"].create(
            {"name": "Audit R2 Unconditional"}
        )
        cls.term = cls.env["account.payment.term"].create(
            {
                "name": "Audit R2 30 Days",
                "line_ids": [
                    Command.create(
                        {"value": "percent", "value_amount": 100.0, "nb_days": 30}
                    )
                ],
            }
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Audit R2 Product", "list_price": 1000.0}
        )
        cls.folder = cls.env["document.document"].create(
            {"name": "Audit R2 Folder", "type": "folder"}
        )
        cls.company_a.credit_folder_id = cls.folder
        cls.doc_type = cls.env["document.type"].create(
            {"name": "Audit R2 Type", "code": "AUDIT_R2", "has_amount": False}
        )
        cls.collateral_type = cls.env["document.type"].create(
            {
                "name": "Audit R2 Collateral Type",
                "code": "AUDIT_R2_COL",
                "has_collateral": True,
            }
        )
        cls.rule_type = cls.env["credit.grade"].create(
            {
                "name": "Audit R2 Rule Type",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "Audit R2 Rule",
                            "document_type_id": cls.doc_type.id,
                            "min_quantity": 1,
                        }
                    )
                ],
            }
        )
        cls.collateral_credit_type = cls.env["credit.grade"].create(
            {
                "name": "Audit R2 Collateral Credit Type",
                "rule_ids": [
                    Command.create(
                        {
                            "name": "Audit R2 Collateral Rule",
                            "document_type_id": cls.collateral_type.id,
                            "min_quantity": 1,
                        }
                    )
                ],
            }
        )

    @classmethod
    def _mkuser(cls, login, groups, both_companies=False):
        companies = [Command.link(cls.env.company.id)]
        if both_companies:
            companies.append(Command.link(cls.company_b.id))
        return cls.env["res.users"].create(
            {
                "name": login,
                "login": login,
                "email": "%s@example.com" % login,
                "company_id": cls.env.company.id,
                "company_ids": companies,
                "group_ids": [Command.link(cls.env.ref(g).id) for g in groups],
            }
        )

    def _grant(self, partner, amount, company=None):
        scoped = partner.with_company(company or self.company_a)
        scoped.write(
            {
                "credit_grade_id": self.unconditional.id,
                "credit_trusted_amount": amount,
            }
        )
        scoped.env.flush_all()
        scoped.invalidate_recordset()
        return scoped.credit_limit

    def _order(self, partner, price, company=None, user=None):
        return (
            self.env["sale.order"]
            .with_user(user or self.credit_manager)
            .with_company(company or self.company_a)
            .create(
                {
                    "partner_id": partner.id,
                    "payment_term_id": self.term.id,
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

    def _compliant_partner(self, name):
        partner = self.env["res.partner"].create(
            {"name": name, "credit_grade_id": self.rule_type.id}
        )
        document = self.env["document.document"].create(
            {
                "name": "%s Doc" % name,
                "folder_id": self.folder.id,
                "partner_id": partner.id,
                "document_type_id": self.doc_type.id,
            }
        )
        partner.env.flush_all()
        partner.invalidate_recordset()
        return partner, document

    def test_wizard_opens_without_an_accounting_group(self):
        self.assertFalse(
            self.credit_manager.has_group("account.group_account_readonly")
        )
        self.assertFalse(self.credit_manager.has_group("account.group_account_invoice"))
        partner = self.env["res.partner"].create({"name": "Audit R2 Wizard"})
        self._grant(partner, 10000.0)
        order = self._order(partner, 15000.0)
        wizard = self._credit_authorization_wizard(order.with_user(self.credit_manager))
        arch = wizard.get_view(
            self.env.ref("account_credit.credit_exceeded_authorization_form").id,
            "form",
        )["arch"]
        kept = [
            fname
            for fname in (
                "partner_credit",
                "credit_limit",
                "amount_available",
                "amount_order",
                "amount_authorized",
            )
            if 'name="%s"' % fname in arch
        ]
        self.assertIn(
            "partner_credit",
            kept,
            "partner_credit is a plain compute read through sudo since the "
            "round-3 company-scoping fix, so the credit manager sees the "
            "receivable instead of the client stripping the gated node",
        )
        wizard.web_read({fname: {} for fname in kept})

    def test_committed_exposure_uses_the_order_company(self):
        partner = self.env["res.partner"].create({"name": "Audit R2 Multi"})
        for company in (self.company_a, self.company_b):
            self._grant(partner, 10000.0, company)
        committed = self._order(partner, 9000.0, company=self.company_b)
        committed.with_context(skip_credit_exceeded_authorization=True).action_confirm()
        order = self._order(partner, 5000.0, company=self.company_b)
        scoped = order.with_context(
            allowed_company_ids=[self.company_a.id, self.company_b.id]
        )
        self.assertEqual(scoped.env.company, self.company_a, "precondition")
        self.assertEqual(scoped.company_id, self.company_b, "precondition")
        self.assertTrue(
            scoped._is_credit_limit_exceeded(),
            "B has 9000 committed plus this 5000 against B's 10000 limit",
        )

    def test_credit_limit_follows_a_shared_input_in_every_company(self):
        partner = self.env["res.partner"].create({"name": "Audit R2 Shared"})
        for company in (self.company_a, self.company_b):
            scoped = partner.with_company(company)
            scoped.write({"credit_grade_id": self.collateral_credit_type.id})
            scoped.env.flush_all()
            scoped.invalidate_recordset()
        document = self.env["document.document"].create(
            {
                "name": "Audit R2 Collateral",
                "folder_id": self.folder.id,
                "partner_id": partner.id,
                "document_type_id": self.collateral_type.id,
                "collateral_amount": 7000.0,
            }
        )
        partner.env.flush_all()
        partner.invalidate_recordset()
        self.assertEqual(
            (
                partner.with_company(self.company_a).credit_limit,
                partner.with_company(self.company_b).credit_limit,
            ),
            (7000.0, 7000.0),
        )
        document.with_company(self.company_a).write({"collateral_amount": 0.0})
        partner.env.flush_all()
        partner.invalidate_recordset()
        self.assertEqual(
            (
                partner.with_company(self.company_a).credit_limit,
                partner.with_company(self.company_b).credit_limit,
            ),
            (0.0, 0.0),
            "a company left at the old collateral is a limit that is too high",
        )

    def test_a_credit_type_set_in_one_company_does_not_leak(self):
        partner = self.env["res.partner"].create({"name": "Audit R2 Scoped"})
        self._grant(partner, 10000.0, self.company_a)
        partner.env.flush_all()
        partner.invalidate_recordset()
        self.assertEqual(
            (
                partner.with_company(self.company_a).credit_limit,
                partner.with_company(self.company_b).credit_limit,
            ),
            (10000.0, 0.0),
        )

    def test_a_credit_manager_cannot_erase_an_authorization(self):
        partner = self.env["res.partner"].create({"name": "Audit R2 Erase"})
        self._grant(partner, 10000.0)
        order = self._order(partner, 15000.0)
        wizard = self._credit_authorization_wizard(order.with_user(self.credit_manager))
        wizard.action_authorize_confirm()
        authorization = (
            self.env["credit.facility"]
            .sudo()
            .search([("partner_id", "=", partner.id), ("source", "=", "authorization")])
        )
        self.assertEqual(len(authorization), 1, "precondition")
        self.assertEqual(
            authorization.user_id, self.credit_manager, "the author is recorded"
        )
        with self.assertRaises(AccessError):
            authorization.with_user(self.credit_manager).unlink()

    def test_a_partner_manager_cannot_grant_a_credit_exception(self):
        partner, _document = self._compliant_partner("Audit R2 Exception")
        with self.assertRaises(AccessError):
            partner.with_user(self.partner_manager).write({"credit_exception": True})

    def test_a_partner_manager_cannot_toggle_legal_process(self):
        partner = self.env["res.partner"].create({"name": "Audit R2 Legal"})
        with self.assertRaises(AccessError):
            partner.with_user(self.partner_manager).action_toggle_legal()

    def test_a_credit_viewer_cannot_raise_the_trusted_amount(self):
        partner = self.env["res.partner"].create({"name": "Audit R2 Trusted"})
        with self.assertRaises(AccessError):
            partner.with_user(self.credit_viewer).write(
                {"credit_trusted_amount": 50000.0}
            )

    def test_a_credit_viewer_cannot_assign_a_credit_condition(self):
        partner = self.env["res.partner"].create({"name": "Audit R2 Condition"})
        with self.assertRaises(AccessError):
            partner.with_user(self.credit_viewer).write(
                {"credit_grade_id": self.rule_type.id}
            )

    def test_the_gate_also_covers_create(self):
        with self.assertRaises(AccessError):
            self.env["res.partner"].with_user(self.partner_manager).create(
                {"name": "Audit R2 Created", "credit_exception": True}
            )

    def test_a_credit_manager_still_writes_the_credit_fields(self):
        partner = self.env["res.partner"].create({"name": "Audit R2 Allowed"})
        partner.with_user(self.credit_manager).write(
            {
                "credit_exception": True,
                "credit_trusted_amount": 1000.0,
                "credit_grade_id": self.unconditional.id,
            }
        )
        partner.invalidate_recordset()
        self.assertTrue(partner.credit_exception)

    def test_a_document_type_flag_refreshes_the_credit_status(self):
        partner, document = self._compliant_partner("Audit R2 Flags")
        self.assertEqual(partner.credit_status, "authorized", "precondition")
        self.doc_type.write({"has_amount": True})
        partner.env.flush_all()
        partner.invalidate_recordset()
        self.assertFalse(document.amount, "precondition: no amount on the document")
        self.assertEqual(partner.credit_status, "review")

    def test_a_credit_note_is_not_blocked_by_the_credit_gate(self):
        partner = self.env["res.partner"].create(
            {"name": "Audit R2 Refund", "credit_grade_id": self.rule_type.id}
        )
        self.assertEqual(partner.credit_status, "review", "precondition")
        refund = self._sale_move(partner, "out_refund")
        refund._check_posting_advisories()

    def test_a_credit_note_is_still_blocked_by_legal_process(self):
        partner = self.env["res.partner"].create({"name": "Audit R2 Refund Legal"})
        partner.write({"credit_legal_hold": True})
        self.assertEqual(partner.credit_status, "legal", "precondition")
        refund = self._sale_move(partner, "out_refund")
        with self.assertRaises(ValidationError):
            refund._check_posting_advisories()

    def test_an_invoice_is_still_blocked_under_review(self):
        partner = self.env["res.partner"].create(
            {"name": "Audit R2 Invoice", "credit_grade_id": self.rule_type.id}
        )
        invoice = self._sale_move(partner, "out_invoice")
        with self.assertRaises(ValidationError):
            invoice._check_posting_advisories()

    def test_the_credit_gate_asks_the_poster_and_not_the_system(self):
        partner = self.env["res.partner"].create(
            {"name": "Audit R2 System Post", "credit_grade_id": self.rule_type.id}
        )
        by_hand = self._sale_move(partner, "out_invoice")
        with self.assertRaises(ValidationError):
            by_hand.action_post()
        self.assertEqual(by_hand.state, "draft")

        by_system = self._sale_move(partner, "out_invoice")
        by_system._post(soft=False)
        self.assertEqual(
            by_system.state,
            "posted",
            "a credit policy is an advisory to the person posting, and a "
            "system posting (POS, subscription, payment) has none to ask",
        )

    def _sale_move(self, partner, move_type):
        return self.env["account.move"].create(
            {
                "move_type": move_type,
                "partner_id": partner.id,
                "invoice_payment_term_id": self.term.id,
                "line_ids": [
                    Command.create(
                        {
                            "product_id": self.product.id,
                            "quantity": 1.0,
                            "price_unit": 500.0,
                        }
                    )
                ],
            }
        )

    def test_the_authorization_search_view_reaches_the_withdrawn_ones(self):
        arch = self.env["credit.facility"].get_view(view_type="search")["arch"]
        self.assertIn("inactive", arch)


@tagged("post_install", "-at_install")
class TestCreditMultiCompanyScoping(TestCreditAuditR2):
    """Round-3 regression cover (parent task 32433): the credit gate and the
    authorization wizard must judge and book against the ORDER's company, not
    the environment's active one."""

    def _order_under_company_a(self, partner, price):
        order = self._order(partner, price, company=self.company_b)
        return order.with_context(
            allowed_company_ids=[self.company_a.id, self.company_b.id],
        ).with_company(self.company_a)

    def test_a_limit_in_the_order_company_is_enforced_from_another(self):
        partner = self.env["res.partner"].create(
            {"name": "MC Scope P1", "is_company": True}
        )
        self._grant(partner, 10000.0, company=self.company_b)

        order = self._order_under_company_a(partner, 50000.0)

        self.assertTrue(
            order._get_credit_limited_partner(),
            "the gate must find the partner's company-B limit even while "
            "company A is active; an empty recordset skips the credit check",
        )
        with self.assertRaises(RedirectWarning, msg="50000 against B's 10000 limit"):
            order.action_confirm()

    def test_the_authorization_is_booked_in_the_order_company(self):
        partner = self.env["res.partner"].create(
            {"name": "MC Scope P2", "is_company": True}
        )
        self._grant(partner, 10000.0, company=self.company_a)
        self._grant(partner, 10000.0, company=self.company_b)

        order = self._order_under_company_a(partner, 50000.0)
        wizard = self._credit_authorization_wizard(order)

        self.assertEqual(wizard.company_id, self.company_b)
        self.assertEqual(
            wizard.credit_limit,
            10000.0,
            "the wizard must show the order company's limit",
        )

        authorization = wizard.with_user(self.credit_manager).action_authorize()

        self.assertEqual(
            authorization.company_id,
            self.company_b,
            "the grant must be booked in the company whose limit it raises",
        )
        self.assertEqual(partner.with_company(self.company_b).credit_limit, 50000.0)
        self.assertEqual(
            partner.with_company(self.company_a).credit_limit,
            10000.0,
            "the other company's limit must not move",
        )
