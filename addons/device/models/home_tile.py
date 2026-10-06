from typing import Any

from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HomeTile(models.AbstractModel):
    _inherit = "home.tile"

    _DEVICES_SHOWN = 6

    @api.model
    def _get_tile_types(self) -> dict[str, dict[str, Any]]:
        return {
            **super()._get_tile_types(),
            "devices": {
                "name": self.env._("Devices"),
                "sizes": ["1x1", "2x1"],
                "model": "device.device",
            },
        }

    @api.model
    def _get_tile_devices_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        Device = self.env["device.device"]
        counts = dict(Device._read_group([], ["connection_state"], ["__count"]))
        silent = Device.search(
            [("connection_state", "!=", "connected")],
            limit=self._DEVICES_SHOWN,
            order="connection_state desc, date_last_data_received, id",
        )
        _debug.logic("devices_tile", **counts)
        return {
            "connected": counts.get("connected", 0),
            "disconnected": counts.get("disconnected", 0),
            "error": counts.get("error", 0),
            "devices": [
                {
                    "id": device.id,
                    "name": device.display_name,
                    "state": device.connection_state,
                    "last_data": device.date_last_data_received,
                }
                for device in silent
            ],
        }
