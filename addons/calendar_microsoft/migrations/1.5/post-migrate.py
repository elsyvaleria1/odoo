from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

from odoo.addons.calendar_sync.migration import (
    CalendarCopySource,
    link_calendar_copies,
)


def migrate(cr, version):
    if not version:
        return
    link_calendar_copies(
        api.Environment(cr, SUPERUSER_ID, {}),
        "microsoft",
        [
            CalendarCopySource(
                "calendar_event",
                "event_id",
                SQL("rec.user_id"),
                {
                    "remote_id": "microsoft_id",
                    "universal_id": "ms_universal_event_id",
                    "remote_master_id": "microsoft_recurrence_master_id",
                },
            ),
            CalendarCopySource(
                "calendar_recurrence",
                "recurrence_id",
                SQL(
                    "(SELECT base.user_id FROM calendar_event base"
                    " WHERE base.id = rec.base_event_id)"
                ),
                {
                    "remote_id": "microsoft_id",
                    "universal_id": "ms_universal_event_id",
                },
            ),
        ],
    )
