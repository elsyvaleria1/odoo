import re
from typing import NamedTuple

from odoo import models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import SQL

_debug = DebugLog(__name__)


class DiscussReach(NamedTuple):
    named: frozenset[int]
    readable: frozenset[int]
    members: tuple[int, ...]


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
        named = self._named_discuss_channel_ids(names).values()
        return websocket.with_context(discuss_reach=websocket._discuss_reach(named))

    def _bus_channels_by_name(self, names: list[str]) -> dict[str, list]:
        result = super()._bus_channels_by_name(names)
        requested = self._named_discuss_channel_ids(names)
        if requested:
            readable = self._discuss_reach(requested.values()).readable
            Channel = self.env["discuss.channel"]
            for name, channel_id in requested.items():
                channel = Channel.browse(channel_id if channel_id in readable else [])
                result[name] = self._discuss_bus_channels(channel)
        return result

    def _named_discuss_channel_ids(self, names: list[str]) -> dict[str, int]:
        requested = {}
        for name in names:
            if match := re.findall(r"discuss\.channel_(\d+)", name):
                requested[name] = int(match[0])
        return requested

    def _discuss_reach(self, channel_ids) -> DiscussReach:
        # which named channels the subscriber reads and which channels it is a
        # member of, in one query: both hooks of a subscription need them, and
        # _bus_context computes them once for the pair
        named = frozenset(channel_ids)
        reach = self.env.context.get("discuss_reach")
        if reach and reach.named == named:
            return reach
        Channel = self.env["discuss.channel"]
        member = Domain("is_member", "=", True)
        query = Channel._search(Domain("id", "in", list(named)) | member)
        id_column = SQL.identifier(query.table, "id")
        rows = self.env.execute_query(
            query.select(
                id_column,
                SQL("%s IN %s", id_column, Channel._search(member).subselect()),
            )
        )
        return DiscussReach(
            named=named,
            readable=frozenset(row_id for row_id, _member in rows if row_id in named),
            members=tuple(row_id for row_id, is_member in rows if is_member),
        )

    def _implicit_bus_channels(self) -> list:
        channels = super()._implicit_bus_channels()
        guest = self.env["mail.guest"]._get_guest_from_context()
        if guest:
            channels.append(guest)
        reach = self.env.context.get("discuss_reach") or self._discuss_reach(())
        members = self.env["discuss.channel"].browse(reach.members)
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
