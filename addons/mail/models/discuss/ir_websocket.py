import re

from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _bus_context(self, names: list[str]):
        # a guest's token names who listens, not what: everything resolves
        # under that guest
        websocket = super()._bus_context(names)
        for name in names:
            if name.startswith("mail.guest_"):
                guest = self.env["mail.guest"]._get_guest_from_token(name.split("_")[1])
                if guest:
                    websocket = websocket.with_context(guest=guest)
        return websocket

    def _bus_channels_by_name(self, names: list[str]) -> dict[str, list]:
        result = super()._bus_channels_by_name(names)
        requested = {}
        for name in names:
            if match := re.findall(r"discuss\.channel_(\d+)", name):
                requested[name] = int(match[0])
        if requested:
            readable = self.env["discuss.channel"].search(
                [("id", "in", list(requested.values()))]
            )
            readable_by_id = {channel.id: channel for channel in readable}
            for name, channel_id in requested.items():
                channel = readable_by_id.get(channel_id, readable.browse())
                result[name] = self._discuss_bus_channels(channel)
        return result

    def _implicit_bus_channels(self) -> list:
        channels = super()._implicit_bus_channels()
        guest = self.env["mail.guest"]._get_guest_from_context()
        if guest:
            channels.append(guest)
        members = self.env["discuss.channel"].search([("is_member", "=", True)])
        _debug.logic(
            "bus_channels_resolved",
            member_channels=len(members),
            guest=guest.id or None,
            internal=not self.env.user.share,
        )
        channels.extend(self._discuss_bus_channels(members))
        return channels

    def _discuss_bus_channels(self, discuss_channels) -> list:
        channels = list(discuss_channels)
        if not self.env.user.share:
            channels.extend((channel, "internal_users") for channel in discuss_channels)
        return channels
