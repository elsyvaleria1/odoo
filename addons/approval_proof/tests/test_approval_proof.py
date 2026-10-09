from odoo.exceptions import UserError, ValidationError
from odoo.tests import new_test_user, tagged
from odoo.tools import SQL
from odoo.tools.authority_keys import strip_authority_keys

from odoo.addons.approval.tests.common import ApprovalCommon

PASSWORD = "approval-proof-1234"


@tagged("post_install", "-at_install")
class TestApprovalProof(ApprovalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.approver_1 | cls.approver_2 | cls.owner_user).password = PASSWORD
        cls.password_method = cls.env.ref("proof.proof_method_password")
        cls.category = cls._make_category(
            name="Cash handover",
            approvers=[cls.approver_1],
            proof_verdicts="approve_refuse",
            proof_method_ids=cls.password_method.ids,
        )

    def _request(self, category=None, **vals):
        return self._prepare_request(category or self.category, amount=1500.0, **vals)

    def _issue(self, request, decision="approve", user=None):
        return request.with_user(user or self.approver_1).action_issue_decision_proof(
            decision
        )

    def _proof(self, params, password=PASSWORD):
        return {
            "token": params["token"],
            "method": "password",
            "payload": {"password": password},
        }

    def _approve(self, request, proof=None, user=None):
        request = request.with_user(user or self.approver_1)
        if proof:
            request.action_approve_with_proof(proof)
        else:
            request.action_approve()

    def _refuse(self, request, proof=None, user=None):
        context = {"skip_wizard": True}
        if proof:
            context["approval_proof"] = proof
        request.with_user(user or self.approver_1).with_context(
            **context
        ).action_refuse()

    def _logs(self, request, verdict):
        return request.sudo().decision_log_ids.filtered(
            lambda log: log.verdict == verdict
        )

    def test_proven_approval_carries_its_evidence(self):
        request = self._request()
        params = self._issue(request)

        self._approve(request, self._proof(params))

        self.assertEqual(request.state, "approved")
        log = self._logs(request, "approved")
        self.assertEqual(log.user_id, self.approver_1)
        evidence = log.evidence_id
        self.assertEqual(
            (evidence.res_model, evidence.res_id, evidence.purpose),
            ("approval.request", request.id, "approval.decision"),
        )
        self.assertEqual(evidence.facts["decision"], "approve")
        self.assertEqual(evidence.facts["amount"], repr(1500.0))
        self.assertEqual(evidence.user_id, self.approver_1)

    def test_the_proof_dialog_shows_what_is_decided(self):
        request = self._request()

        params = self._issue(request)

        labels = dict(params["summary"])
        self.assertEqual(labels["Decision"], "Approve")
        self.assertEqual(labels["Request"], request.display_name)
        self.assertIn("1,500.00", labels["Amount"])
        self.assertEqual([m["code"] for m in params["methods"]], ["password"])

    def test_a_decision_without_proof_is_refused(self):
        request = self._request()

        with self.assertRaisesRegex(UserError, "needs a proof that it is you"):
            self._approve(request)
        self.assertEqual(request.state, "pending")

    def test_a_category_asking_no_proof_decides_as_before(self):
        category = self._make_category(name="Plain", approvers=[self.approver_1])
        request = self._request(category)

        self.assertIsNone(self._issue(request))
        self._approve(request)

        self.assertEqual(request.state, "approved")
        self.assertFalse(self._logs(request, "approved").evidence_id)

    def test_a_refusal_needs_its_own_proof(self):
        request = self._request()

        with self.assertRaisesRegex(UserError, "needs a proof that it is you"):
            self._refuse(request)
        self._refuse(request, self._proof(self._issue(request, "refuse")))

        self.assertEqual(request.state, "refused")
        evidence = (
            self._logs(request, "refused")
            .filtered(lambda log: not log.principal_id)
            .evidence_id
        )
        self.assertEqual(evidence.facts["decision"], "refuse")

    def test_refusals_stay_free_where_only_approvals_need_a_proof(self):
        self.category.proof_verdicts = "approve"
        request = self._request()

        self._refuse(request)

        self.assertEqual(request.state, "refused")

    def test_a_proof_given_to_approve_cannot_refuse(self):
        request = self._request()
        params = self._issue(request, "approve")

        with self.assertRaisesRegex(UserError, "changed since you were asked"):
            self._refuse(request, self._proof(params))
        self.assertEqual(request.state, "pending")

    def test_a_figure_moved_after_the_proof_was_asked_refuses_it(self):
        request = self._request()
        params = self._issue(request)
        self.env.cr.execute(
            SQL("UPDATE approval_request SET amount = 1400 WHERE id = %s", request.id)
        )
        request.invalidate_recordset(["amount"])

        with self.assertRaisesRegex(UserError, "changed since you were asked"):
            self._approve(request, self._proof(params))

    def test_a_wrong_password_leaves_the_request_pending(self):
        request = self._request()
        params = self._issue(request)

        with self.assertRaisesRegex(UserError, "Incorrect password"):
            self._approve(request, self._proof(params, password="wrong"))

        self.assertEqual(request.state, "pending")
        self._approve(request, self._proof(params))
        self.assertEqual(request.state, "approved")

    def test_someone_elses_proof_does_not_decide(self):
        category = self._make_category(
            name="Two parties",
            approvers=[self.approver_1, self.approver_2],
            proof_verdicts="approve",
            proof_method_ids=self.password_method.ids,
        )
        request = self._request(category)
        params = self._issue(request, user=self.approver_2)

        with self.assertRaisesRegex(UserError, "issued to someone else"):
            self._approve(request, self._proof(params), user=self.approver_1)

    def test_only_a_pending_approver_is_asked_for_a_proof(self):
        request = self._request()

        with self.assertRaises(UserError):
            self._issue(request, user=self.approver_2)

    def test_bulk_approval_does_not_decide_a_proof_category(self):
        request = self._request()

        result = request.with_user(self.approver_1).action_approve_bulk()

        self.assertEqual(request.state, "pending")
        self.assertIn("needs a proof", str(result))

    def test_request_readers_read_the_proof_others_do_not(self):
        request = self._request()
        self._approve(request, self._proof(self._issue(request)))
        evidence = self._logs(request, "approved").evidence_id
        outsider = new_test_user(self.env, login="approval_proof_outsider")

        owner_view = request.with_user(self.owner_user).decision_log_ids.evidence_id

        self.assertEqual(owner_view.with_user(self.owner_user).method_code, "password")
        self.assertFalse(
            self.env["proof.evidence"]
            .with_user(outsider)
            .search([("id", "=", evidence.id)])
        )

    def test_a_proof_category_needs_methods_and_no_consent(self):
        with self.assertRaisesRegex(ValidationError, "choose the proof methods"):
            self._make_category(name="No methods", proof_verdicts="approve")
        with self.assertRaisesRegex(ValidationError, "cannot be approved by consent"):
            self._make_category(
                name="Consent",
                proof_verdicts="approve",
                proof_method_ids=self.password_method.ids,
                consent_approval_hours=4,
            )

    def test_a_proof_cannot_ride_in_on_a_client_context(self):
        context = {"approval_proof": {"token": "x"}, "approval_proof_evidence_id": 1}

        stripped = strip_authority_keys(context, "call_kw")

        self.assertNotIn("approval_proof", stripped)
        self.assertNotIn("approval_proof_evidence_id", stripped)

    def test_approving_from_the_activity_row_takes_the_proof(self):
        request = self._request()
        row = request.approver_ids.filtered(lambda a: a.user_id == self.approver_1)
        params = row.with_user(self.approver_1).action_issue_decision_proof("approve")

        row.with_user(self.approver_1).action_approve_with_proof(self._proof(params))

        self.assertEqual(request.state, "approved")
        self.assertTrue(self._logs(request, "approved").evidence_id)

    def test_a_category_without_delegation_refuses_a_delegate(self):
        self.category.allow_delegation = False
        request = self._request()
        row = request.approver_ids.filtered(lambda a: a.user_id == self.approver_1)

        self.assertFalse(row._may_delegate_to(self.approver_2))
        with self.assertRaisesRegex(ValidationError, "cannot hand their approval"):
            self._delegate_row(row, self.approver_2)
