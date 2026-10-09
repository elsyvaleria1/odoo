import logging

from odoo import api, models, tools
from odoo.exceptions import AccessError

from odoo.addons.bus.tools.channel_capability import (
    channel_capability,
    channel_target,
    register_channel_scope,
    token_revision,
)

_logger = logging.getLogger(__name__)

# A box hears only what is sent to it, and an answer goes back only to whoever
# asked: a request leaves with its session id wrapped in a signed route naming
# the requester's reply channel, the box echoes the id, the server unwraps it.
BOX_CHANNEL = register_channel_scope(
    "iot.box",
    purpose="the requests sent to one IoT box: print jobs, display content, "
    "payment-terminal commands",
    lifetime="until the box is paired again and its token changes",
)
REPLY_CHANNEL = register_channel_scope(
    "iot.reply",
    purpose="the IoT boxes' answers to the requests of one user or one kiosk",
    lifetime="undated for a user; a kiosk's until its self-ordering token is rotated",
)
REPLY_ROUTE = tools.register_signed_scope(
    "iot.reply_route",
    purpose="carry through an IoT box the reply channel its answer returns to",
    lifetime="undated: one request's round trip",
)
ROUTE_SEPARATOR = "|"


class IotChannel(models.AbstractModel):
    _name = "iot.channel"
    _description = "The Websocket IoT Channel"

    def get_iot_channel(self):
        self._check_iot_channel_access()
        return self._reply_channel(self._user_reply_key())

    @api.model
    def send_message(self, message, message_type="iot_action"):
        self._check_iot_channel_access()
        self._send_message(message, message_type, reply_key=self._user_reply_key())

    def _check_iot_channel_access(self) -> None:
        if not self.env.su and not self.env.user._is_internal():
            raise AccessError(self.env._("Only internal users can reach IoT boxes."))

    def _user_reply_key(self) -> str:
        return f"user.{self.env.uid}"

    def _kiosk_reply_key(self, pos_config) -> str:
        token = pos_config.self_ordering_access_token or ""
        return f"kiosk.{pos_config.id}.{token_revision(token)}"

    def _reply_channel(self, reply_key) -> str:
        return channel_capability(self.env, REPLY_CHANNEL, reply_key)

    def _box_channel(self, box) -> str:
        return channel_capability(self.env, BOX_CHANNEL, self._box_key(box))

    def _box_key(self, box) -> str:
        return f"{box.id}.{token_revision(box.token or '')}"

    def _send_message(self, message, message_type="iot_action", reply_key=None):
        """Send ``message`` to the boxes it names; an answer to it returns to
        ``reply_key``'s channel, and to nobody when it is None."""
        identifiers = set(message.get("iot_identifiers") or [])
        if message.get("iot_identifier"):
            identifiers.add(message["iot_identifier"])
        if reply_key and message.get("session_id"):
            message = {
                **message,
                "session_id": self._wrap_session_id(reply_key, message["session_id"]),
            }
        boxes = (
            self.env["iot.box"].sudo().search([("identifier", "in", list(identifiers))])
        )
        for box in boxes:
            self.env["bus.bus"]._sendone(
                channel_target(self.env, BOX_CHANNEL, self._box_key(box)),
                message_type,
                message,
            )

    def _send_reply(self, message, message_type) -> None:
        """Return a box's answer to whoever asked, and drop one whose route
        is missing or forged."""
        route = self._unwrap_session_id(message.get("session_id"))
        if route is None:
            _logger.debug(
                "IoT %s answer without a valid route dropped (session %r)",
                message_type,
                message.get("session_id"),
            )
            return
        reply_key, session_id = route
        self.env["bus.bus"]._sendone(
            channel_target(self.env, REPLY_CHANNEL, reply_key),
            message_type,
            {**message, "session_id": session_id},
        )

    def _wrap_session_id(self, reply_key, session_id) -> str:
        session_id = str(session_id)
        signature = tools.hmac(self.env, REPLY_ROUTE, (reply_key, session_id))
        return ROUTE_SEPARATOR.join((reply_key, session_id, signature))

    def _unwrap_session_id(self, wrapped) -> tuple[str, str] | None:
        parts = str(wrapped or "").split(ROUTE_SEPARATOR)
        if len(parts) != 3:
            return None
        reply_key, session_id, signature = parts
        if not tools.is_hmac_valid(
            self.env, REPLY_ROUTE, (reply_key, session_id), signature
        ):
            return None
        return reply_key, session_id
