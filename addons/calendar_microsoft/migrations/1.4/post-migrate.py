from odoo import SUPERUSER_ID, api

from odoo.addons.calendar_sync.migration import adopt_settings_columns


def migrate(cr, version):
    if not version:
        return
    adopt_settings_columns(
        api.Environment(cr, SUPERUSER_ID, {}),
        "microsoft",
        {
            "sync_token": "microsoft_calendar_sync_token",
            "stopped": "microsoft_synchronization_stopped",
            "last_sync_date": "microsoft_last_sync_date",
        },
    )
