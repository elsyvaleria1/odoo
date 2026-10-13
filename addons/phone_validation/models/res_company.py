from odoo import models


class ResCompany(models.Model):
    _inherit = "res.company"

    def write(self, vals):
        if "country_id" not in vals:
            return super().write(vals)
        result = super(
            ResCompany, self.with_context(phone_rekeyed_by_company=True)
        ).write(vals)
        self.env["phone.number"]._rekey_local_sanitized()
        return result
