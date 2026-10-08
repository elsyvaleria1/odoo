from odoo import models

PRIVACY_GATED_MODELS = frozenset({"project.project", "project.task"})


class AccessLink(models.Model):
    _inherit = "access.link"

    def _record_refusal(self) -> str:
        reason = super()._record_refusal()
        if reason or self.res_model not in PRIVACY_GATED_MODELS:
            return reason
        # read as the policy reads it: whoever presents the token, the
        # project's privacy and collaborators decide
        record = (
            self.env["ir.access"]
            ._access_evaluator(self.res_model)
            .browse(self.res_id)
            .exists()
        )
        if record and not record._admits_link_partner(self.partner_id):
            return "privacy"
        return ""
