from odoo import models


class HrVersion(models.Model):
    _inherit = "hr.version"

    def _get_schedule_exceptions(self, start_dt, end_dt):
        return (
            super()
            ._get_schedule_exceptions(start_dt, end_dt)
            .filtered(lambda l: l.holiday_id.payslip_state != "blocked")
        )
