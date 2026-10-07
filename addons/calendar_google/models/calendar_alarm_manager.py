from odoo import api, models
from odoo.tools import SQL


class AlarmManager(models.AbstractModel):
    _inherit = "calendar.alarm_manager"

    @api.model
    def _get_notify_alert_extra_conditions(self):
        base = super()._get_notify_alert_extra_conditions()
        return SQL(
            """%s AND NOT EXISTS (
                SELECT 1
                  FROM calendar_sync_link link
                  JOIN calendar_sync_account account ON account.id = link.account_id
                 WHERE link.event_id = event.id
                   AND account.provider = 'google'
                   AND link.remote_id IS NOT NULL
            )""",
            base,
        )
