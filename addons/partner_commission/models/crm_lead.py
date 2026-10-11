from odoo import models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def action_new_quotation(self):
        action = super().action_new_quotation()
        action["context"]["default_referrer_id"] = self.partner_assigned_id.id
        return action
