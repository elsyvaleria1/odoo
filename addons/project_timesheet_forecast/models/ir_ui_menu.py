from odoo import models


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _get_blacklisted_menu_ids(self):
        res = super()._get_blacklisted_menu_ids()
        if not (
            self.env.user.has_group("planning.group_planning_manager")
            and self.env.user.has_group("hr_timesheet.group_hr_timesheet_approver")
        ):
            res.append(
                self.env.ref(
                    "project_timesheet_forecast.menu_project_timesheet_forecast_report_analysis"
                ).id
            )
        return res
