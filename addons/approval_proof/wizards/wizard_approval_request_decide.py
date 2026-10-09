from typing import Any

from odoo import models


class WizardApprovalRequestDecide(models.TransientModel):
    _inherit = "wizard.approval.request.decide"

    def action_confirm_refuse_with_proof(
        self, proof: dict[str, Any]
    ) -> dict[str, Any] | None:
        self.check_singleton()
        return self.with_context(approval_proof=proof).action_confirm_refuse()
