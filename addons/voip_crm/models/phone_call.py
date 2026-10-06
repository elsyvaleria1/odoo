from odoo import fields, models


class PhoneCall(models.Model):
    _inherit = "phone.call"

    opportunity_count = fields.Integer(
        related="partner_id.opportunity_count",
        related_sudo=False,
        groups="sale.group_sale_salesman",
    )

    def voip_action_view_opportunity(self):
        action = self.partner_id.action_view_opportunity()
        if not self.partner_id:
            action["context"] = {
                "default_phone": self.phone_number,
            }
        return action
