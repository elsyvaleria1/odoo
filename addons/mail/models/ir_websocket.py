import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta

from odoo import models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools.misc import is_valid_limited_field_access_token

from odoo.addons.mail.models.mixin_mail_presence import PRESENCE_SCOPE
from odoo.addons.mail.tools.discuss import add_guest_to_context

PRESENCE_CHANNEL_PREFIX = "odoo-presence-"
PRESENCE_CHANNEL_REGEX = re.compile(
    rf"{PRESENCE_CHANNEL_PREFIX}"
    r"(?P<model>res\.partner|mail\.guest)_(?P<record_id>\d+)"
    r"(?:-(?P<token>[a-f0-9]{64}o0x[a-f0-9]+))?$"
)
_logger = logging.getLogger(__name__)
_debug = DebugLog(__name__)


class IrWebsocket(models.AbstractModel):
    _inherit = "ir.websocket"

    def _serve_ir_websocket(self, event_name: str, data: dict) -> None:
        super()._serve_ir_websocket(event_name, data)
        if event_name == "update_presence":
            self._update_mail_presence(**data)

    @add_guest_to_context
    def _subscribe(self, og_data: dict) -> None:
        super()._subscribe(og_data)

    @add_guest_to_context
    def _update_mail_presence(self, inactivity_period: int) -> None:
        partner, guest = self.env["res.partner"]._get_current_persona()
        if not partner and not guest:
            return
        _debug.lifecycle(
            "presence_updated",
            partner=partner.id or None,
            guest=guest.id or None,
            inactivity_ms=inactivity_period,
        )
        self.env["mail.presence"]._try_update_presence(
            self.env.user if partner else guest, inactivity_period
        )

    def _bus_channels_by_name(self, names: list[str]) -> dict[str, list]:
        result = super()._bus_channels_by_name(names)
        requested = defaultdict(dict)
        for name in names:
            if not name.startswith(PRESENCE_CHANNEL_PREFIX):
                continue
            if not (match := re.match(PRESENCE_CHANNEL_REGEX, name)):
                _debug.logic("presence_channel_malformed", channel=name[:80])
                _logger.warning("Malformed presence channel: %s", name)
                continue
            model, record_id, token = match.groups()
            requested[model][name] = (int(record_id), token or "")
        allowed = {
            model: self._presence_readable(model, list(by_name.values()))
            for model, by_name in requested.items()
        }
        for model, by_name in requested.items():
            allowed_by_id = {record.id: record for record in allowed[model]}
            for name, (record_id, _token) in by_name.items():
                record = allowed_by_id.get(record_id)
                result[name] = [(record, "presence")] if record else []
        _debug.logic(
            "presence_subscriptions",
            partners_asked=len(requested["res.partner"]),
            partners_allowed=len(allowed.get("res.partner", ())),
            guests_asked=len(requested["mail.guest"]),
            guests_allowed=len(allowed.get("mail.guest", ())),
        )
        return result

    def _presence_readable(self, model: str, ids_and_tokens: list[tuple]):
        """The records of ``model`` whose presence this subscriber may hear: it
        reads them, or holds their im_status token."""
        tokens = dict(ids_and_tokens)
        records = self.env[model].with_context(active_test=False).sudo()
        records = records.search([("id", "in", list(tokens))]).sudo(False)
        readable = set(records._filtered_access("read")._ids)
        return records.filtered(
            lambda r: (
                r.id in readable
                or is_valid_limited_field_access_token(
                    r, "im_status", tokens[r.id], scope=PRESENCE_SCOPE
                )
            )
        )

    def _implicit_bus_channels(self) -> list:
        channels = super()._implicit_bus_channels()
        partner, guest = self.env["res.partner"]._get_current_persona()
        channels.extend(
            (persona, "presence") for persona in (partner, guest) if persona
        )
        return channels

    def _prepare_subscribe_data(self, channels: list, last: int) -> dict:
        data = super()._prepare_subscribe_data(channels, last)
        heard = defaultdict(list)
        for channel in data["channels"]:
            if isinstance(channel, tuple) and channel[1:] == ("presence",):
                heard[channel[0]._name].append(channel[0].id)
        presence_domain = Domain(
            "last_poll", ">", datetime.now() - timedelta(seconds=2)
        ) & (
            Domain(
                "user_id",
                "in",
                self.env["res.partner"]
                .browse(heard["res.partner"])
                .with_context(active_test=False)
                .sudo()
                .user_ids.ids,
            )
            | Domain("guest_id", "in", heard["mail.guest"])
        )
        data["missed_presences"] = (
            self.env["mail.presence"].sudo().search(presence_domain)
        )
        return data

    def _after_subscribe_data(self, data: dict) -> None:
        super()._after_subscribe_data(data)
        current_partner, current_guest = self.env["res.partner"]._get_current_persona()
        if current_partner or current_guest:
            data["missed_presences"]._send_presence(
                bus_target=current_partner or current_guest
            )

    def _on_websocket_closed(self, cookies: dict) -> None:
        super()._on_websocket_closed(cookies)
        if self.env.user and not self.env.user._is_public():
            _debug.lifecycle("websocket_closed", user=self.env.user.id)
            self.env["mail.presence"].search(
                [("user_id", "=", self.env.uid)]
            ).status = "offline"
        token = cookies.get(self.env["mail.guest"]._cookie_name, "")
        if guest := self.env["mail.guest"]._get_guest_from_token(token):
            _debug.lifecycle("websocket_closed", guest=guest.id)
            guest.sudo().presence_ids.status = "offline"
