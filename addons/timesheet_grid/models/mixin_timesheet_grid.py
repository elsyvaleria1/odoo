from odoo import models
from odoo.tools import float_round


class MixinTimesheetGrid(models.AbstractModel):
    _name = "mixin.timesheet.grid"
    _description = "Timesheet Grid mixin"

    def get_planned_and_worked_hours(self):
        company = self.env.company
        uom = company.hr_timesheet_config_id.timesheet_encode_uom_id
        day_uom = self.env.ref("base.product_uom_day")
        rounding = (
            len(
                str(
                    format(
                        company.hr_timesheet_config_id.timesheet_encode_uom_id.rounding,
                        "f",
                    )
                )
                .split(".")[1]
                .split("1")[0]
            )
            + 1
        )
        hours_per_day = company.resource_calendar_id.hours_per_day

        def convert_hours_to_company_uom(hours):
            return (
                float_round(hours / hours_per_day, precision_digits=rounding)
                if uom == day_uom
                else hours
            )

        records = self.search_read(
            self.get_domain_planned_and_worked_hours(),
            ["id", self.get_allocated_hours_field()] + self.get_fields_worked_hours(),
        )

        records_per_id = {key: {} for key in self.ids}
        uom_name = uom.name.lower()
        for record in records:
            records_per_id[record["id"]] = {
                "allocated_hours": convert_hours_to_company_uom(
                    record[self.get_allocated_hours_field()]
                ),
                "uom": uom_name,
                "worked_hours": convert_hours_to_company_uom(
                    sum(record[field] for field in self.get_fields_worked_hours())
                ),
            }
        return records_per_id

    def get_domain_planned_and_worked_hours(self):
        return [("id", "in", self.ids)]
