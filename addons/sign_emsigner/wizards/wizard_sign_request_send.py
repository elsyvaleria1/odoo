from odoo import api, models
from odoo.exceptions import UserError


class WizardSignRequestSend(models.TransientModel):
    _inherit = "wizard.sign.request.send"
    _description = "Sign send request"

    def sign_directly(self):
        if self.env.context.get("sign_all") and len(self.signer_ids) > 1:
            has_emsigner_role = any(
                signer.role_id.auth_method == "emsigner"
                for signer in self.signer_ids[:-1]
            )
            if has_emsigner_role:
                raise UserError(
                    self.env._(
                        "Emsigner role cannot be signed first. Please keep emsigner as last signer."
                    )
                )
        return super().sign_directly()

    @api.depends("only_autofill_readonly", "signers_count", "is_user_signer")
    def _compute_display_download_button(self) -> None:
        for wiz in self:
            if wiz.signer_ids[:1].role_id.auth_method == "emsigner":
                wiz.display_download_button = False
            else:
                super()._compute_display_download_button()
