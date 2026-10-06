from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    billable_time_target = fields.Float(
        string="Billing Time Target",
        groups="hr_timesheet.group_hr_timesheet_user",
    )
    show_billable_time_target = fields.Boolean(
        related="company_id.timesheet_show_rates"
    )

    @api.model
    def get_all_billable_time_targets(self):
        if (
            self.env.user.has_group("hr_timesheet.group_hr_timesheet_user")
            and self.env.company.timesheet_show_rates
        ):
            _debug.perf.count("billable_time_targets_read", company=self.env.company)
            return self.sudo().search_read(
                [("company_id", "=", self.env.company.id)], ["billable_time_target"]
            )
        _debug.logic("billable_time_targets_hidden", user=self.env.user)
        return []

    _check_billable_time_target = models.Constraint(
        "CHECK(billable_time_target >= 0)",
        "The billable time target cannot be negative.",
    )
