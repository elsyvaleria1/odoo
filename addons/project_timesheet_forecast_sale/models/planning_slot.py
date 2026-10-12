from datetime import timedelta

from odoo import models
from odoo.libs.numbers import float_compare


class PlanningSlot(models.Model):
    _inherit = "planning.slot"

    def _init_remaining_hours_to_plan(self, remaining_hours_to_plan):
        res = super()._init_remaining_hours_to_plan(remaining_hours_to_plan)
        if self.project_id and not self.sale_line_id.product_id.planning_enabled:
            if self.project_id.allocated_hours == 0:
                return res
            if self.project_id not in remaining_hours_to_plan:
                remaining_hours_to_plan[self.project_id] = (
                    self.project_id.allocated_hours
                    - self.project_id.sudo().total_forecast_time
                )
            if (
                float_compare(
                    remaining_hours_to_plan[self.project_id], 0.0, precision_digits=2
                )
                != 1
            ):
                return False
        return res

    def _update_remaining_hours_to_plan_and_values(
        self, remaining_hours_to_plan, values
    ):
        res = super()._update_remaining_hours_to_plan_and_values(
            remaining_hours_to_plan, values
        )
        if self.project_id and not self.sale_line_id.product_id.planning_enabled:
            if self.project_id.allocated_hours == 0:
                return res
            if (
                float_compare(
                    remaining_hours_to_plan[self.project_id], 0.0, precision_digits=2
                )
                != 1
            ):
                return False
            allocated_hours = (
                values["end_datetime"] - values["start_datetime"]
            ).total_seconds() / 3600
            ratio = self.allocated_percentage / 100.00
            remaining_hours = min(
                remaining_hours_to_plan[self.project_id] / ratio, allocated_hours
            )
            values["end_datetime"] = values["start_datetime"] + timedelta(
                hours=remaining_hours
            )
            values.pop("allocated_hours", None)
            remaining_hours_to_plan[self.project_id] -= remaining_hours * ratio
        return res
