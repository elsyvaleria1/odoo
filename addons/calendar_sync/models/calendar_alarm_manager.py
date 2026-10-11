from odoo import api, models
from odoo.tools import SQL


class AlarmManager(models.AbstractModel):
    _inherit = "calendar.alarm_manager"

    @api.model
    def _get_notify_alert_extra_conditions(self):
        base = super()._get_notify_alert_extra_conditions()
        codes = list(self.env["calendar.sync.account"]._engine_providers())
        if not codes:
            return base
        return SQL(
            """%s AND NOT EXISTS (
                SELECT 1
                  FROM calendar_sync_link link
                  JOIN calendar_sync_account account ON account.id = link.account_id
                 WHERE link.event_id = event.id
                   AND link.remote_id IS NOT NULL
                   AND account.provider = ANY(%s)
            )""",
            base,
            codes,
        )
