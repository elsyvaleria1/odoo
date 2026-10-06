from odoo import api, models


class AppointmentInvite(models.Model):
    _inherit = "appointment.invite"

    def _prepare_url_params(self) -> dict:
        applicant_code = self.env.context.get("applicant_code")
        return {
            **super()._prepare_url_params(),
            **({"applicant_code": applicant_code} if applicant_code else {}),
        }

    @api.depends_context("applicant_code")
    def _compute_book_url_params(self):
        return super()._compute_book_url_params()
