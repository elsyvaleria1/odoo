import logging
from itertools import batched

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {"active_test": False, "dont_notify": True})
    Recurrence = env["calendar.recurrence"]
    rrule_field = Recurrence._fields["rrule"]
    kept = []
    for ids in batched(
        Recurrence.search([("rrule", "!=", False)]).ids, 1000, strict=False
    ):
        for recurrence in Recurrence.browse(ids):
            try:
                values = recurrence._rrule_parse(
                    recurrence.rrule,
                    recurrence.dtstart,
                    recurrence._get_timezone(),
                    allday=recurrence._is_allday(),
                )
            except ValueError:
                _logger.warning(
                    "calendar: recurrence %s holds an unreadable rule %r, left as is",
                    recurrence.id,
                    recurrence.rrule,
                )
                continue
            if not values["custom_rrule"]:
                continue
            with env.protecting([rrule_field], recurrence):
                recurrence.write(values)
            kept.append(recurrence.id)
        env.invalidate_all()
    if kept:
        _logger.info(
            "calendar: %s recurrence(s) keep a rule their options cannot express: %s",
            len(kept),
            kept,
        )
