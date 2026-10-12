import logging

from odoo import SUPERUSER_ID, api, fields
from odoo.tools import float_compare

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    exceptions = env["resource.schedule.exception"]
    closures = exceptions.search(
        [
            ("resource_id", "=", False),
            ("company_id", "=", False),
            ("calendar_id.company_id", "=", False),
            ("date_to", ">", fields.Datetime.now()),
        ]
    )
    if not closures:
        return
    leaves = env["hr.leave"].search(
        exceptions._get_domain_for_periods(closures._get_schedule_scopes())
    )
    durations = leaves._get_durations()
    stale = leaves.filtered(
        lambda leave: any(
            float_compare(counted, stored, precision_digits=4)
            for counted, stored in zip(
                durations.get(leave.id, (leave.number_of_days, leave.number_of_hours)),
                (leave.number_of_days, leave.number_of_hours),
                strict=True,
            )
        )
    )
    exceptions._reevaluate_leave_durations(stale)
    if stale:
        _logger.info(
            "Recounted %d time off(s) that %d shared-calendar closure(s) still "
            "to come now give back to every company on the calendar",
            len(stale),
            len(closures),
        )
