from odoo import api, models


class HrLeaveReportCalendar(models.Model):
    _inherit = "hr.leave.report.calendar"

    @api.model
    def _gantt_unavailability(self, field_name, res_ids, start, stop, scale):
        return self.env["hr.leave"]._gantt_unavailability(
            field_name, res_ids, start, stop, scale
        )
