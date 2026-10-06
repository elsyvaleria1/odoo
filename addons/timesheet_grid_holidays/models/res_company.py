from odoo import api, models
from odoo.fields import Domain


class Company(models.Model):
    _inherit = "res.company"

    @api.model
    def _get_domain_timesheet_reminder(self):
        return Domain.AND(
            [
                super()._get_domain_timesheet_reminder(),
                [("holiday_id", "=", False), ("global_leave_id", "=", False)],
            ]
        )
