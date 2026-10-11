from odoo import api, models


class WizardSignRequestSend(models.TransientModel):
    _inherit = "wizard.sign.request.send"

    @api.depends("only_autofill_readonly", "signers_count", "is_user_signer")
    def _compute_display_download_button(self) -> None:
        for wiz in self:
            if wiz.signer_ids[:1].role_id.auth_method == "itsme":
                wiz.display_download_button = False
            else:
                super()._compute_display_download_button()
