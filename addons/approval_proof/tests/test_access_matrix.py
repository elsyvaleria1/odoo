from odoo.tests import tagged

from odoo.addons.approval.tests.common import pool_step
from odoo.addons.base.tests.access_matrix import AccessMatrixCase, Cell, Persona


@tagged("post_install", "-at_install", "access_matrix")
class TestApprovalProofAccessMatrix(AccessMatrixCase):
    personas = {
        "requester_a": Persona(),
        "approver_a": Persona("approval.group_approval_approver"),
        "colleague_a": Persona(),
        "manager_a": Persona("approval.group_approval_manager"),
    }
    cells = (
        Cell(
            "proof.evidence",
            "decision_evidence",
            note="the proof behind a decision is read wherever the request is",
            requester_a="r",
            approver_a="r",
            manager_a="r",
        ),
    )

    @classmethod
    def create_matrix_records(cls):
        approver = cls.users["approver_a"]
        category = cls.env["approval.category"].create(
            {
                "name": "Matrix handover",
                "approval_minimum": 1,
                "privacy_visibility": "private",
                "step_ids": pool_step([(approver.id, True, 10)]),
                "proof_verdicts": "approve",
                "proof_method_ids": cls.env.ref("proof.proof_method_password").ids,
            }
        )
        request = cls.env["approval.request"].create(
            {
                "category_id": category.id,
                "request_owner_id": cls.users["requester_a"].id,
                "amount": 10.0,
            }
        )
        request.action_confirm()
        params = request.with_user(approver).action_issue_decision_proof("approve")
        proof = {
            "token": params["token"],
            "method": "password",
            "payload": {"password": approver.login},
        }
        request.with_user(approver).with_context(approval_proof=proof).action_approve()
        return {"decision_evidence": request.sudo().decision_log_ids.evidence_id}
