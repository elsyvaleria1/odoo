from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

from odoo.addons.calendar_sync.migration import RemoteIdSource, link_remote_ids


def migrate(cr, version):
    if not version:
        return
    link_remote_ids(
        api.Environment(cr, SUPERUSER_ID, {}),
        "google",
        [
            RemoteIdSource(
                "calendar_event",
                "event_id",
                SQL("rec.user_id, rec.create_uid"),
            ),
            RemoteIdSource(
                "calendar_recurrence",
                "recurrence_id",
                SQL(
                    "(SELECT base.user_id FROM calendar_event base"
                    " WHERE base.id = rec.base_event_id), rec.create_uid"
                ),
            ),
        ],
        "google_id",
    )
