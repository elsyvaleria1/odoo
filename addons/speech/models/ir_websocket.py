import re

from odoo import models

LIVE_CHANNEL = re.compile(r"^speech\.live/([a-z0-9_.]+)/(\d+)$")


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _bus_channels_by_name(self, names):
        result = super()._bus_channels_by_name(names)
        for name in names:
            match = LIVE_CHANNEL.match(name)
            if match and self._is_live_model(match.group(1)):
                record = self.env[match.group(1)].browse(int(match.group(2))).exists()
                result[name] = [
                    (record, "live") for record in record._filtered_access("read")
                ]
        return result

    def _is_live_model(self, model: str) -> bool:
        registry = self.env.registry
        return model in registry and issubclass(
            registry[model], registry["mixin.speech.live"]
        )
