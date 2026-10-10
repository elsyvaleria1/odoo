import logging
import time

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
    lifetime="ROUTE_LIFETIME from the request, the device events it owns included",
)
ROUTE_SEPARATOR = "|"
# An upstream box authenticates none of its answers: a route a box ever echoed
# could otherwise be replayed through it for good.
ROUTE_LIFETIME = 24 * 3600
# What a web client may ask of a box; the rest is the server's to send.
CLIENT_MESSAGE_TYPES = frozenset({"iot_action", "webrtc_offer", "test_connection"})
# Each is a verb of iot.box, granted by its ir.access row.
ADMIN_MESSAGE_TYPES = frozenset({"remote_debug"})
# Boxes run upstream's iot_drivers, which answers these without echoing the
# session id: their answer returns to whoever last sent one to that box.
UNROUTED_ANSWER_TYPES = frozenset({"webrtc_offer", "remote_debug"})


class IotChannel(models.AbstractModel):
    _name = "iot.channel"
    _description = "The Websocket IoT Channel"

    def get_iot_channel(self):
        self._check_iot_channel_access()
        return self._reply_channel(self._user_reply_key())

    @api.model
    def send_message(self, message, message_type="iot_action"):
        self._check_iot_channel_access()
        if message_type in ADMIN_MESSAGE_TYPES:
            self._check_box_verb(message, message_type)
        elif message_type not in CLIENT_MESSAGE_TYPES:
            raise AccessError(
                self.env._(
                    "You may not send %(type)s to an IoT box.", type=message_type
                )
            )
        self._send_message(message, message_type, reply_key=self._user_reply_key())

    def _check_box_verb(self, message, verb) -> None:
        identifiers = set(message.get("iot_identifiers") or [])
        if message.get("iot_identifier"):
            identifiers.add(message["iot_identifier"])
        boxes = self.env["iot.box"].search([("identifier", "in", list(identifiers))])
        if len(boxes) != len(identifiers):
            raise AccessError(self.env._("You cannot reach this IoT box."))
        boxes.check_access(verb)

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
        boxes = (
            self.env["iot.box"].sudo().search([("identifier", "in", list(identifiers))])
        )
        for box in boxes:
            sent = message
            if reply_key and message.get("session_id"):
                route = self._wrap_session_id(
                    reply_key, message["session_id"], box.identifier
                )
                sent = {**message, "session_id": route}
            if reply_key and message_type in UNROUTED_ANSWER_TYPES:
                keys = box.unrouted_reply_keys or {}
                if keys.get(message_type) != reply_key:
                    box.unrouted_reply_keys = {**keys, message_type: reply_key}
            self.env["bus.bus"]._sendone(
                channel_target(self.env, BOX_CHANNEL, self._box_key(box)),
                message_type,
                sent,
            )

    def _send_reply(self, message, message_type, box=None, unrouted=None) -> None:
        """Return a box's answer to whoever asked, and drop one whose route
        is missing or forged. An answer upstream boxes send without a route
        to a request of type ``unrouted`` goes to its last sender to ``box``."""
        route = self._unwrap_session_id(
            message.get("session_id"), message.get("iot_box_identifier")
        )
        if route is None and box and unrouted in UNROUTED_ANSWER_TYPES:
            reply_key = (box.unrouted_reply_keys or {}).get(unrouted)
            if reply_key:
                route = (reply_key, message.get("session_id"))
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

    def _wrap_session_id(
        self, reply_key, session_id, box_identifier, issued=None
    ) -> str:
        session_id = str(session_id)
        issued = str(int(time.time() if issued is None else issued))
        signature = tools.hmac(
            self.env, REPLY_ROUTE, (reply_key, session_id, box_identifier, issued)
        )
        return ROUTE_SEPARATOR.join((reply_key, session_id, issued, signature))

    def _unwrap_session_id(self, wrapped, box_identifier) -> tuple[str, str] | None:
        parts = str(wrapped or "").split(ROUTE_SEPARATOR)
        if len(parts) != 4 or not box_identifier or not parts[2].isdigit():
            return None
        reply_key, session_id, issued, signature = parts
        if time.time() - int(issued) > ROUTE_LIFETIME:
            return None
        if not tools.is_hmac_valid(
            self.env,
            REPLY_ROUTE,
            (reply_key, session_id, box_identifier, issued),
            signature,
        ):
            return None
        return reply_key, session_id
