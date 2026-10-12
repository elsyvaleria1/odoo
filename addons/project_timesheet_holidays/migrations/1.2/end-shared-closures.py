import logging

from odoo import SUPERUSER_ID, api, fields

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    closures = env["resource.schedule.exception"].search(
        [
            ("resource_id", "=", False),
            ("company_id", "=", False),
            ("calendar_id.company_id", "=", False),
            ("date_to", ">", fields.Datetime.now()),
        ]
    )
    employees = env["hr.employee"].search(
        [("resource_calendar_id", "in", closures.calendar_id.ids)]
    )
    if not employees:
        return
    lines = closures._generate_public_time_off_timesheets(employees)
    if lines:
        _logger.info(
            "Booked %d time-off line(s) for the employees of other companies on "
            "the calendars of %d shared closure(s) still to come",
            len(lines),
            len(closures),
        )
