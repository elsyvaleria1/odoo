from odoo import models
from odoo.http import SessionExpiredException
from odoo.service import security
from odoo.tools.misc import OrderedSet

from ..tools.channel_capability import resolve_capability
from ..websocket import wsrequest
from .bus import channel_with_db, dispatch

MAX_SUBSCRIBED_CHANNELS = 4096
MAX_CHANNEL_LENGTH = 512


class IrWebsocket(models.AbstractModel):
    _name = "ir.websocket"
    _description = "websocket message handling"

    def _get_bus_channels(self, channels):
        broadcast = channel_with_db(self.env.cr.dbname, "broadcast")
        channels = [*channels, broadcast, *self.env.user.all_group_ids]
        if not self.env.user._is_public():
            channels = [*channels, self.env.user.partner_id]
        return channels

    def _serve_ir_websocket(self, event_name, data):
        pass

    def _prepare_subscribe_data(self, channels, last):
        if not isinstance(channels, (list, tuple)) or not all(
            isinstance(c, str) for c in channels
        ):
            raise ValueError("bus.Bus only string channels are allowed.")
        if len(channels) > MAX_SUBSCRIBED_CHANNELS:
            raise ValueError(
                f"bus.Bus subscription is limited to {MAX_SUBSCRIBED_CHANNELS} "
                f"channels, got {len(channels)}."
            )
        if any(len(channel) > MAX_CHANNEL_LENGTH for channel in channels):
            raise ValueError(
                f"bus.Bus channel names are limited to {MAX_CHANNEL_LENGTH} characters."
            )
        if not isinstance(last, int) or isinstance(last, bool):
            raise ValueError("bus.Bus subscription 'last' must be an integer.")
        last = max(0, last)
        newest = self.env["bus.bus"].sudo()._bus_last_id() if last else 0
        reset = last > newest
        channels = [resolve_capability(self.env, c) or c for c in channels]
        # What an override did not turn into a channel of its own is a name the
        # client made up, and a made-up name is one anyone can say.
        channels = [
            c for c in self._get_bus_channels(channels) if not isinstance(c, str)
        ]
        # A watermark past the newest row was drawn from another history (a
        # database restored or recreated under the same name): the client is
        # told the one it now stands at, or it would keep it forever.
        return {
            "channels": OrderedSet(channels),
            "last": 0 if reset else last,
            "watermark_reset": newest if reset else None,
        }

    def _after_subscribe_data(self, data):
        pass

    def _subscribe(self, og_data) -> None:
        if not isinstance(og_data, dict) or "channels" not in og_data:
            raise ValueError(
                "bus.Bus subscribe data must be a dict with a 'channels' key."
            )
        data = self._prepare_subscribe_data(og_data["channels"], og_data.get("last", 0))
        dispatch.subscribe(
            data["channels"], data["last"], self.env.registry.db_name, wsrequest.ws
        )
        # Only to a client that asks: an IoT box reads every frame as a list
        # of notifications.
        if data["watermark_reset"] is not None and og_data.get(
            "report_watermark_reset"
        ):
            wsrequest.ws._send(
                {"event": "watermark_reset", "last": data["watermark_reset"]}
            )
        self._after_subscribe_data(data)

    def _on_websocket_closed(self, cookies):
        pass

    def _authenticate(self):
        if wsrequest.session.uid is not None:
            if not security.is_session_valid(
                wsrequest.session, self.env, wsrequest, fresh_primary_cr=self.env.cr
            ):
                raise SessionExpiredException
        else:
            public_user_id = self.env["ir.model.data"]._xmlid_to_res_id(
                "base.public_user"
            )
            wsrequest.update_env(user=public_user_id)
