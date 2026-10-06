from odoo import fields, models


class PhoneCall(models.Model):
    _inherit = "phone.call"

    subscription_count = fields.Integer(
        related="partner_id.subscription_count",
        related_sudo=False,
        groups="sale.group_sale_salesman",
    )

    def voip_action_view_subscription(self):
        self.check_singleton()
        return self.partner_id.open_related_subscription()
