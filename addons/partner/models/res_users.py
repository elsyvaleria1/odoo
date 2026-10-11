from odoo import api, models, modules


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _get_activity_groups(self):
        activities = super()._get_activity_groups()
        for activity in activities:
            if activity["model"] != "res.partner":
                continue
            activity["icon"] = modules.module.Manifest.for_addon("partner").icon
        return activities
