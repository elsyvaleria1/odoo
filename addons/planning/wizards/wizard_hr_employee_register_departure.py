from datetime import datetime, time, timedelta

from odoo import models


class WizardHrEmployeeRegisterDeparture(models.TransientModel):
    _inherit = "wizard.hr.employee.register.departure"

    def action_register_departure(self):
        action = super().action_register_departure()

        departure_date = datetime.combine(
            self.departure_date + timedelta(days=1), time.min
        )
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
