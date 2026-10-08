from odoo import api, fields, models

from odoo.addons.calendar_microsoft.utils.calendar_microsoft import CALENDAR_SCOPE
from odoo.addons.calendar_sync.provider import (
    CalendarSyncCapabilities,
    CalendarSyncProvider,
)

MICROSOFT = CalendarSyncProvider(
    code="microsoft",
    label="Outlook",
    key="calendar_microsoft",
    service="integration_microsoft.service_microsoft",
    scope=CALENDAR_SCOPE,
    paused_param="microsoft_calendar_sync_paused",
    adapter="calendar.sync.adapter.microsoft",
    capabilities=CalendarSyncCapabilities(series_inserts=False, answer_endpoint=True),
    range_param="calendar_microsoft.sync.range_days",
)


class CalendarSyncAccount(models.Model):
    _inherit = "calendar.sync.account"

    provider = fields.Selection(
        selection_add=[("microsoft", "Outlook")],
        ondelete={"microsoft": "cascade"},
    )

    @api.model
    def _calendar_sync_providers(self) -> dict:
        return {**super()._calendar_sync_providers(), "microsoft": MICROSOFT}
