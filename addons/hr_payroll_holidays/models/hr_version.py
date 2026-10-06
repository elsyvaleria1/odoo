from odoo import models


class HrVersion(models.Model):
    _inherit = "hr.version"

    def _get_schedule_exceptions(self, start_dt, end_dt):
        # prevent leaves that are associated with a blocked payslip to be taken
        # into account, as they will be deferred lated.
        return (
            super()
            ._get_schedule_exceptions(start_dt, end_dt)
            .filtered(lambda l: l.holiday_id.payslip_state != "blocked")
        )
