import logging
from datetime import UTC, timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.datetime import timezone
from odoo.tools.date_utils import utcnow

_logger = logging.getLogger(__name__)

_DEFAULT_TZ = "America/Mexico_City"


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    lunch_out = fields.Datetime(help="Time the employee clocked out for lunch.")
    lunch_in = fields.Datetime(help="Time the employee clocked back in from lunch.")
    lunch_hours = fields.Float(
        compute="_compute_lunch_hours",
        precompute=True,
        store=True,
        readonly=True,
    )

    @api.depends("lunch_in", "lunch_out")
    def _compute_lunch_hours(self) -> None:
        for attendance in self:
            if attendance.lunch_in and attendance.lunch_out:
                delta = attendance.lunch_in - attendance.lunch_out
                attendance.lunch_hours = delta.total_seconds() / 3600.0
            else:
                attendance.lunch_hours = 0.0

    @api.constrains("lunch_in", "lunch_out")
    def _check_lunch_times(self) -> None:
        for attendance in self:
            if attendance.lunch_out:
                if (
                    not attendance.check_in
                    or attendance.lunch_out < attendance.check_in
                ):
                    raise ValidationError(
                        self.env._(
                            '"Lunch Out" time cannot be earlier than "Check In" time.'
                        )
                    )
                if attendance.check_out and attendance.lunch_out > attendance.check_out:
                    raise ValidationError(
                        self.env._(
                            '"Lunch Out" time cannot be later than "Check Out" time.'
                        )
                    )

            if attendance.lunch_in:
                if not attendance.lunch_out:
                    raise ValidationError(
                        self.env._(
                            'Cannot have a "Lunch In" time without a "Lunch Out" time.'
                        )
                    )
                if attendance.lunch_in < attendance.lunch_out:
                    raise ValidationError(
                        self.env._(
                            '"Lunch In" time cannot be earlier than "Lunch Out" time.'
                        )
                    )
                if attendance.check_out and attendance.lunch_in > attendance.check_out:
                    raise ValidationError(
                        self.env._(
                            '"Lunch In" time cannot be later than "Check Out" time.'
                        )
                    )

    def _cron_auto_checkout_at_day_end(self) -> None:
        _logger.info("Starting cron job: Auto-checkout for attendances left open...")

        today_start_utc = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        open_attendances = self.search(
            [
                ("check_in", "<", today_start_utc),
                ("check_out", "=", False),
            ]
        )

        for att in open_attendances:
            try:
                with self.env.cr.savepoint():
                    self._auto_checkout_one(att)
            except Exception:
                _logger.exception(
                    "Auto-checkout failed for attendance %s; skipping.", att.id
                )
        _logger.info("Finished cron job: Auto-checkout.")

    def _auto_checkout_one(self, att) -> None:
        employee = att.employee_id
        calendar = employee.resource_calendar_id
        if calendar.schedule_type == "fully_flexible":
            _logger.info(
                "Skipping auto-checkout for attendance %s: a fully flexible "
                "schedule has no end of day.",
                att.id,
            )
            return
        tz = timezone(employee.tz or _DEFAULT_TZ)

        check_in_local = att.check_in.replace(tzinfo=UTC).astimezone(tz)
        weekday = str(check_in_local.weekday())

        day_attendances = calendar.attendance_ids.filtered(
            lambda a, wd=weekday: a.dayofweek == wd
        )

        day_start_local = check_in_local.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end_of_day_utc = (
            (day_start_local + timedelta(days=1)).astimezone(UTC).replace(tzinfo=None)
        )

        if day_attendances:
            checkout_time_local = day_start_local + timedelta(
                hours=max(day_attendances.mapped("hour_to"))
            )
            checkout_time_utc = checkout_time_local.astimezone(UTC).replace(tzinfo=None)
        else:
            _logger.info(
                "Attendance %s was opened on a day the calendar of '%s' does not "
                "cover; closing it at the end of that day.",
                att.id,
                calendar.name,
            )
            checkout_time_utc = end_of_day_utc

        if checkout_time_utc < att.check_in:
            checkout_time_utc = end_of_day_utc

        att.write({"check_out": checkout_time_utc})
        att.message_post(
            body=self.env._(
                "This attendance was automatically closed by the system at the end of the day."
            )
        )
        _logger.info(
            "Automatically checked out attendance %s for employee %s.",
            att.id,
            employee.name,
        )
