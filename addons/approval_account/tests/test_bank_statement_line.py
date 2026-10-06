from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged

from .common import AccountApprovalCommon
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.approval.tests.common import add_category_approver


@tagged("post_install", "-at_install")
class TestBankStatementLineRelease(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]
        cls.partner = cls.env["res.partner"].sudo().create({"name": "BSL Vendor"})

        cls.category = (
            cls.env["approval.category"]
            .sudo()
            .create(
                {
                    "name": "Payment with BSL",
                    "approval_type": "accounting",
                    "approval_minimum": 1,
                    "has_amount": "required",
                    "has_partner": "required",
                    "has_bsl": "required",
                },
            )
        )

        cls.approver_user = (
            cls.env["res.users"]
            .sudo()
            .create(
                {
                    "name": "BSL Approver",
                    "login": "bsl_approver",
                    "email": "bsl_approver@test.com",
                    "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
                },
            )
        )
        add_category_approver(cls.category, cls.approver_user, required=True)

        cls.bsl = (
            cls.env["account.bank.statement.line"]
            .sudo()
            .create(
                {
                    "journal_id": cls.bank_journal.id,
                    "date": "2026-05-01",
                    "amount": 100.0,
                    "payment_ref": "Test BSL Release",
                },
            )
        )

    def _new_request(self, name, bsl=None):
        vals = {
            "name": name,
            "category_id": self.category.id,
            "partner_id": self.partner.id,
            "amount": 100.0,
            "date": "2026-05-01",
        }
        if bsl:
            vals["bank_statement_line_id"] = bsl.id
        return self.env["approval.request"].sudo().create(vals)

    def _force_request_state(self, request, target_state):
        request.approver_ids.sudo()._record_decision(target_state)
        request.invalidate_recordset(["state"])
        self.assertEqual(request.state, target_state)

    def _selectable_bsl(self, request):
        return (
            self.env["account.bank.statement.line"]
            .sudo()
            .search(
                [
                    "|",
                    ("id", "=", request.bank_statement_line_id.id),
                    (
                        "approval_request_ids",
                        "not any",
                        [("state", "not in", ("refused", "cancelled"))],
                    ),
                ],
            )
        )

    def test_active_approval_blocks_bsl(self):
        approval_a = self._new_request("Request A", bsl=self.bsl)
        approval_b = self._new_request("Request B")

        self.assertNotIn(
            self.bsl,
            self._selectable_bsl(approval_b),
            "A bank line held by a live approval must not be offered to siblings",
        )
        self.assertIn(
            self.bsl,
            self._selectable_bsl(approval_a),
            "A request always keeps its own line selectable",
        )

    def test_refused_approval_releases_bsl(self):
        approval_a = self._new_request("Request A", bsl=self.bsl)
        approval_b = self._new_request("Request B")

        self.assertNotIn(self.bsl, self._selectable_bsl(approval_b))

        self._force_request_state(approval_a, "refused")

        self.assertIn(
            self.bsl,
            self._selectable_bsl(approval_b),
            "Refused approvals must release their BSL back to the pool",
        )

    def test_live_bsl_claim_is_exclusive(self):
        self._new_request("Holder", bsl=self.bsl)
        with self.assertRaises(ValidationError):
            self._new_request("Challenger", bsl=self.bsl)

    def test_refused_bsl_claim_is_reclaimable(self):
        approval_a = self._new_request("Holder", bsl=self.bsl)
        self._force_request_state(approval_a, "refused")

        approval_b = self._new_request("Challenger", bsl=self.bsl)
        self.assertEqual(approval_b.bank_statement_line_id, self.bsl)


@tagged("post_install", "-at_install")
class TestBankStatementLineRequired(AccountApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.bank_journal = cls.company_data["default_journal_bank"]

        cls.category_bsl_required = cls.env["approval.category"].create(
            {
                "name": "Payment (BSL required)",
                "approval_type": "accounting",
                "approval_minimum": 1,
                "has_amount": "required",
                "has_partner": "required",
                "has_bsl": "required",
            },
        )
        cls.category_bsl_optional = cls.env["approval.category"].create(
            {
                "name": "Payment (BSL optional)",
                "approval_type": "accounting",
                "approval_minimum": 1,
                "has_amount": "required",
                "has_partner": "required",
                "has_bsl": "optional",
            },
        )
        for category in (cls.category_bsl_required, cls.category_bsl_optional):
            add_category_approver(category, cls.approver, required=True)

        cls.bsl = cls.env["account.bank.statement.line"].create(
            {
                "journal_id": cls.bank_journal.id,
                "date": "2026-06-01",
                "amount": 100.0,
                "payment_ref": "Test BSL required",
            },
        )

    def _new_request(self, name, category, bsl=None):
        vals = {
            "name": name,
            "category_id": category.id,
            "partner_id": self.partner_a.id,
            "amount": 100.0,
            "date": "2026-06-01",
        }
        if bsl:
            vals["bank_statement_line_id"] = bsl.id
        request = self.env["approval.request"].create(vals)
        request.action_confirm()
        return request

    def test_confirm_allowed_without_bsl(self):
        request = self._new_request("No BSL yet", self.category_bsl_required)
        self.assertEqual(
            request.state,
            "pending",
            "Requests are confirmed before treasury selects the bank line",
        )

    def test_approve_blocked_without_bsl(self):
        request = self._new_request("Blocked", self.category_bsl_required)
        with self.assertRaises(UserError, msg="Approval must be blocked"):
            request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, "pending", "Request must stay pending")

    def test_approve_passes_with_bsl(self):
        request = self._new_request(
            "Approved",
            self.category_bsl_required,
            bsl=self.bsl,
        )
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, "approved")

    def test_optional_bsl_does_not_block(self):
        request = self._new_request("Optional", self.category_bsl_optional)
        request.with_user(self.approver).action_approve()
        self.assertEqual(request.state, "approved")

    def test_consent_cron_skips_request_without_bsl(self):
        category = self.env["approval.category"].create(
            {
                "name": "Consent (BSL required)",
                "approval_type": "general",
                "approval_minimum": 1,
                "has_amount": "required",
                "has_partner": "required",
                "has_bsl": "required",
                "consent_approval_hours": 1,
            },
        )
        add_category_approver(category, self.approver, required=True)
        request = self._new_request("Consent", category)
        request.sudo().date_confirmed = fields.Datetime.now() - timedelta(hours=2)

        self.env["approval.request"].cron_consent_approval()
        self.assertEqual(
            request.state,
            "pending",
            "Cron must skip the request while the required BSL is missing",
        )

        request.bank_statement_line_id = self.bsl
        self.env["approval.request"].cron_consent_approval()
        self.assertEqual(
            request.state,
            "approved",
            "Cron must auto-approve once the required BSL is set",
        )
