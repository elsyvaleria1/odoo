from odoo import Command, api, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    @api.model
    def _ai_prepare_lead_creation_values(self, vals):
        values = super()._ai_prepare_lead_creation_values(vals)
        if channel := self.env.context.get("discuss_channel"):
            values["origin_channel_id"] = channel.id
            # avoid another bridge module just for that
            if "website" in self.env and (visitor := channel.livechat_visitor_id):
                values["visitor_ids"] = [Command.link(visitor.id)]
        return values
