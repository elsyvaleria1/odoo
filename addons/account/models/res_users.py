from odoo import api, models


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _get_activity_groups(self):
        activities = super()._get_activity_groups()
        for activity in activities:
            if activity["model"] == "account.return":
                activity |= {
                    "name": self.env._("Tax Returns"),
                    "view_type": "kanban",
                }
        return activities
