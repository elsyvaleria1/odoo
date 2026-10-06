from typing import Any

from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HomeTile(models.AbstractModel):
    _inherit = "home.tile"

    _AGENDA_EVENTS_SHOWN = 6

    @api.model
    def _get_tile_types(self) -> dict[str, dict[str, Any]]:
        return {
            **super()._get_tile_types(),
            "agenda": {
                "name": self.env._("Today"),
                "sizes": ["1x1", "2x1"],
                "model": "calendar.event",
            },
        }

    @api.model
    def _get_tile_agenda_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        events = self.env["calendar.event"].search_fetch(
            self.env.user._systray_get_calendar_event_domain(),
            ["name", "start", "stop", "allday", "location"],
            order="start",
            limit=self._AGENDA_EVENTS_SHOWN + 1,
        )
        _debug.logic("agenda_tile", events=len(events))
        return {
            "events": [
                {
                    "id": event.id,
                    "name": event.name,
                    "start": event.start,
                    "stop": event.stop,
                    "allday": event.allday,
                    "location": event.location or "",
                }
                for event in events[: self._AGENDA_EVENTS_SHOWN]
            ],
            "more": len(events) > self._AGENDA_EVENTS_SHOWN,
        }
