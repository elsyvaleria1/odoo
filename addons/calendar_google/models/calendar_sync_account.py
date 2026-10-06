from odoo import api, fields, models

from odoo.addons.calendar_google.utils.calendar_google import CALENDAR_SCOPE
from odoo.addons.calendar_sync.provider import CalendarSyncProvider

GOOGLE = CalendarSyncProvider(
    code="google",
    label="Google",
    key="calendar_google",
    service="integration_google.service_google",
    scope=CALENDAR_SCOPE,
    paused_param="google_calendar_sync_paused",
)


class CalendarSyncAccount(models.Model):
    _inherit = "calendar.sync.account"

    provider = fields.Selection(
        selection_add=[("google", "Google")],
        ondelete={"google": "cascade"},
    )

    @api.model
    def _calendar_sync_providers(self) -> dict:
        return {**super()._calendar_sync_providers(), "google": GOOGLE}
