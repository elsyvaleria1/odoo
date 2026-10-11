from odoo import api, models


class ResourceCalendar(models.Model):
    _inherit = "resource.calendar"

    _ATTENDANCE_DERIVING_FIELDS = frozenset(
        {"tz", "two_weeks_calendar", "schedule_type"}
    )

    def write(self, vals):
        res = super().write(vals)
        if not self._ATTENDANCE_DERIVING_FIELDS.isdisjoint(vals):
            self._refresh_derived_attendance_fields()
        return res

    def _refresh_derived_attendance_fields(self) -> None:
        if not self:
            return
        attendances = (
            self.env["hr.attendance"]
            .sudo()
            .search([("employee_id.version_ids.resource_calendar_id", "in", self.ids)])
        )
        if not attendances:
            return
        for name in ("date", "worked_hours"):
            self.env.add_to_compute(attendances._fields[name], attendances)


class ResourceCalendarAttendance(models.Model):
    _inherit = "resource.calendar.attendance"

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.calendar_id._refresh_derived_attendance_fields()
        return lines

    def write(self, vals):
        calendars = self.calendar_id
        res = super().write(vals)
        (calendars | self.calendar_id)._refresh_derived_attendance_fields()
        return res

    def unlink(self):
        calendars = self.calendar_id
        res = super().unlink()
        calendars._refresh_derived_attendance_fields()
        return res
