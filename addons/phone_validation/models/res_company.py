from odoo import models


class ResCompany(models.Model):
    _inherit = "res.company"

    def write(self, vals):
        result = super().write(vals)
        if "country_id" in vals:
            self.env["phone.number"]._rekey_local_sanitized()
        return result
