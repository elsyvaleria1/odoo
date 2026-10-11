from odoo import SUPERUSER_ID, api

from odoo.addons.calendar_sync.migration import adopt_settings_columns


def migrate(cr, version):
    if not version:
        return
    adopt_settings_columns(
        api.Environment(cr, SUPERUSER_ID, {}),
        "google",
        {
            "sync_token": "google_calendar_sync_token",
            "stopped": "google_synchronization_stopped",
        },
        dropped=("google_calendar_cal_id",),
    )
