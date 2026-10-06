from odoo import api, models
from odoo.exceptions import RedirectWarning, UserError
from odoo.fields import Domain


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    def _is_timer_hidden(self) -> bool:
        self.check_singleton()
        return bool(super()._is_timer_hidden() or self.task_id.sudo().is_timeoff_task)

    def action_merge_timesheets(self) -> dict:
        if self.holiday_id:
            if (
                not self.env.user.has_group("hr_holidays.group_hr_holidays_user")
                and self.env.user not in self.holiday_id.sudo().user_id
            ):
                raise UserError(
                    self.env._(
                        "You cannot merge timesheets that are linked to time off requests. Please use the Time Off application to modify or cancel your time off requests instead."
                    )
                )
            warning_msg = self.env._(
                "You cannot merge timesheets that are linked to time off requests. Please use the Time Off application to modify or cancel your time off requests instead."
            )
            action = self._get_redirect_action()
            raise RedirectWarning(warning_msg, action, self.env._("View Time Off"))
        return super().action_merge_timesheets()

    @api.model
    def grid_update_cell(self, domain, measure_field_name, value):
        return super().grid_update_cell(
            Domain.AND([domain, [("holiday_id", "=", False)]]),
            measure_field_name,
            value,
        )

    def action_timer_start(self):
        if self.task_id.sudo().is_timeoff_task:
            raise UserError(
                self.env._(
                    "You cannot start a timer for a task that is linked to a time off request. To request additional time off, please use the Time Off application."
                )
            )
        return super().action_timer_start()
