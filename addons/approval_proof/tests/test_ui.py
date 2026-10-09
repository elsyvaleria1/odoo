from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.approval.tests.common import pool_step


@tagged("post_install", "-at_install")
class TestApprovalProofUi(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.approver = new_test_user(
            cls.env,
            login="approval_proof_tour_approver",
            groups="base.group_user,approval.group_approval_approver",
        )
        owner = new_test_user(cls.env, login="approval_proof_tour_owner")
        category = cls.env["approval.category"].create(
            {
                "name": "Cash handover tour",
                "approval_minimum": 1,
                "step_ids": pool_step([(cls.approver.id, True, 10)]),
                "proof_verdicts": "approve_refuse",
                "proof_method_ids": cls.env.ref("proof.proof_method_password").ids,
            }
        )
        cls.env["approval.refusal.reason"].create({"name": "Count does not match"})
        cls.request = cls.env["approval.request"].create(
            {
                "category_id": category.id,
                "request_owner_id": owner.id,
                "amount": 1500.0,
            }
        )
        cls.request.action_confirm()

    def _decision_evidence(self, verdict):
        logs = self.request.decision_log_ids.filtered(
            lambda log: log.verdict == verdict and not log.principal_id
        )
        return logs.evidence_id

    def test_approving_from_the_form_asks_for_the_proof(self):
        self.start_tour(
            f"/odoo/approval.request/{self.request.id}",
            "approval_proof_approve_tour",
            login=self.approver.login,
        )

        self.assertEqual(self.request.state, "approved")
        self.assertEqual(self._decision_evidence("approved").user_id, self.approver)

    def test_approving_from_the_activity_asks_for_the_proof(self):
        self.start_tour(
            f"/odoo/approval.request/{self.request.id}",
            "approval_proof_activity_tour",
            login=self.approver.login,
        )

        self.assertEqual(self.request.state, "approved")
        self.assertEqual(self._decision_evidence("approved").user_id, self.approver)

    def test_refusing_through_the_wizard_asks_for_the_proof(self):
        self.start_tour(
            f"/odoo/approval.request/{self.request.id}",
            "approval_proof_refuse_tour",
            login=self.approver.login,
        )

        self.assertEqual(self.request.state, "refused")
        evidence = self._decision_evidence("refused")
        self.assertEqual(evidence.facts["decision"], "refuse")
