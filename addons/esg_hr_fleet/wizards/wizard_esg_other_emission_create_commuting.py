from odoo import Command, api, fields, models


class WizardEsgOtherEmissionCreateCommuting(models.TransientModel):
    _name = "wizard.esg.other.emission.create.commuting"
    _description = "Generate emitted emissions from employee commuting"

    date_start = fields.Date(
        string="Emissions Period",
        required=True,
    )
    date_end = fields.Date(
        export_string_translation=False,
        required=True,
    )
    conflicting_emission_ids = fields.Many2many(
        comodel_name="esg.other.emission",
        export_string_translation=False,
        compute="_compute_conflicting_emission_ids",
    )

    @api.depends("date_start", "date_end")
    def _compute_conflicting_emission_ids(self) -> None:
        for wizard in self:
            if not wizard.date_start or not wizard.date_end:
                wizard.conflicting_emission_ids = [Command.clear()]
                continue

            overlapping_emissions = self.env["esg.other.emission"].search(
                [
                    ("is_fleet", "=", True),
                    ("date", "<=", wizard.date_end),
                    ("date_end", ">=", wizard.date_start),
                ]
            )
            wizard.conflicting_emission_ids = overlapping_emissions

    def _get_total_commuting_emissions(self) -> int | float:
        self.check_singleton()
        if not self.date_start or not self.date_end:
            return 0.0

        total_co2 = 0.0
        vehicles = self.env["resource.asset"].search(
            [("kind_id.code", "=", "vehicle"), ("company_id", "=", self.env.company.id)]
        )
        vehicle_by_resource = {vehicle.resource_id: vehicle for vehicle in vehicles}
        period_start = fields.Datetime.to_datetime(self.date_start)
        period_end = fields.Datetime.to_datetime(self.date_end)
        assignments = self.env["resource.assignment"].search(
            [
                ("custody_role", "=", "operator"),
                ("resource_id", "in", vehicles.resource_id.ids),
                ("date_start", "<=", period_end),
                "|",
                ("date_end", ">=", period_start),
                ("date_end", "=", False),
            ]
        )
        employees = self.env["hr.employee"].search(
            [("resource_id", "in", assignments.assignee_id.ids)]
        )
        employee_by_resource = {
            employee.resource_id: employee for employee in employees
        }

        for assignment in assignments:
            employee = employee_by_resource.get(assignment.assignee_id)
            vehicle = vehicle_by_resource.get(assignment.resource_id)
            if not employee or not vehicle:
                continue

            overlap_start = max(assignment.date_start.date(), self.date_start)
            overlap_end = min(
                assignment.date_end.date() if assignment.date_end else self.date_end,
                self.date_end,
            )

            days = (overlap_end - overlap_start).days + 1
            daily_km = (employee.distance_home_work or 0) * 2
            work_ratio = vehicle.company_id.weekly_days_at_office / 7.0

            total_co2 += days * daily_km * work_ratio * vehicle.co2 / 1_000

        return int(total_co2)

    def action_save(self):
        emission_factor = self.env.ref("esg_hr_fleet.employee_commuting_factor")
        self.env["esg.other.emission"].create(
            {
                "name": self.env._("Employee Commuting"),
                "date": self.date_start,
                "date_end": self.date_end,
                "esg_emission_factor_id": emission_factor.id,
                "quantity": self._get_total_commuting_emissions(),
                "note": self.env._(
                    "Employee commuting from %(start_date)s to %(end_date)s",
                    start_date=fields.Date.to_string(self.date_start),
                    end_date=fields.Date.to_string(self.date_end),
                ),
                "is_fleet": True,
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": self.env._("Emission successfully created"),
                "next": {
                    "type": "ir.actions.act_window_close",
                },
            },
        }

    def action_see_conflicting_emissions(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "esg.carbon.emission.report",
            "name": self.env._("Conflicting Emissions"),
            "views": [[False, "list"], [False, "form"]],
            "domain": [("id", "in", self.conflicting_emission_ids.ids)],
        }
