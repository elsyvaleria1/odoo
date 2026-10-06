from datetime import datetime, time, timedelta

from odoo import models


class WizardHrEmployeeRegisterDeparture(models.TransientModel):
    _inherit = "wizard.hr.employee.register.departure"

    def action_register_departure(self):
        action = super().action_register_departure()

        departure_date = datetime.combine(
            self.departure_date + timedelta(days=1), time.min
        )
        # No end_datetime pre-filter here: departure_date is naive and only
        # _manage_archived_resources() knows how to convert it to UTC (per
        # slot/employee timezone) to compare it against end_datetime.
        planning_slots = (
            self.env["planning.slot"]
            .sudo()
            .search(
                [
                    ("employee_id", "in", self.employee_ids.ids),
                ]
            )
        )
        planning_slots._manage_archived_resources(departure_date)
        return action
