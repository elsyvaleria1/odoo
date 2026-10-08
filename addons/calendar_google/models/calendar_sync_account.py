from odoo import api, fields, models

from odoo.addons.calendar_google.utils.calendar_google import CALENDAR_SCOPE
from odoo.addons.calendar_sync.provider import (
    CalendarSyncCapabilities,
    CalendarSyncProvider,
)

GOOGLE = CalendarSyncProvider(
    code="google",
    label="Google",
    key="calendar_google",
    service="integration_google.service_google",
    scope=CALENDAR_SCOPE,
    paused_param="google_calendar_sync_paused",
    adapter="calendar.sync.adapter.google",
    capabilities=CalendarSyncCapabilities(shared_ids=True, client_insert_id=True),
    range_param="calendar_google.sync.range_days",
    icon="/calendar/static/src/booking/img/google-calendar.svg",
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
