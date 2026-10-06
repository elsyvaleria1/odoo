from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardSignRequestSend(models.TransientModel):
    _inherit = "wizard.sign.request.send"

    def _get_default_signer(self):
        reference_doc = self.env.context.get("default_reference_doc")
        if reference_doc:
            model, id = reference_doc.split(",")
            if model == "hr.applicant":
                _debug.logic(
                    "sign_default_signer_from_applicant",
                    applicant_id=int(id),
                    partner=self.env["hr.applicant"].browse(int(id)).partner_id,
                )
                return self.env["hr.applicant"].browse(int(id)).partner_id
        _debug.logic(
            "sign_default_signer_delegated",
            reason="no_applicant_reference",
            reference_doc=reference_doc,
        )
        return super()._get_default_signer()
