from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def write(self, vals):
        commercial_partners = {}
        for partner in self:
            commercial_partners[partner.id] = partner.commercial_partner_id

        res = super().write(vals)

        partners_with_new_commercial = self.env["res.partner"]
        for partner in self:
            if commercial_partners[partner.id] != partner.commercial_partner_id:
                partners_with_new_commercial |= partner

        if partners_with_new_commercial:
            linked_tokens_sudo = (
                self.env["payment.token"]
                .sudo()
                .search(
                    [
                        ("partner_id", "in", partners_with_new_commercial.ids),
                        ("provider_id.code", "=", "custom"),
                        ("provider_id.custom_mode", "=", "sepa_direct_debit"),
                    ]
                )
            )
            linked_tokens_sudo.active = False

        return res
