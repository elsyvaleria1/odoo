import urllib.parse

from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_partner_navigate(self) -> dict:
        self.check_singleton()
        encoded_address = urllib.parse.quote_plus(self.contact_address_complete)
        url = f"https://www.google.com/maps/dir/?api=1&destination={encoded_address}"
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}
