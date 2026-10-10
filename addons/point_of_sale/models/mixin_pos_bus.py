import uuid

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.bus.tools.channel_capability import (
    channel_capability,
    channel_target,
    register_channel_scope,
    token_revision,
)

_debug = DebugLog(__name__)

# The audiences a person holds: a till or a kitchen display is opened by a user
# who reads its record. A customer display or a tracking screen is a device,
# whose link is the capability.
USER_AUDIENCES = frozenset({"till"})


def _holds_pos_channel(env, key) -> bool:
    model, record_id, audience, _revision = _split_pos_bus_key(key)
    if audience not in USER_AUDIENCES:
        return True
    if model not in env or not record_id.isdigit():
        return False
    record = env[model].browse(int(record_id)).exists()
    return bool(record) and record.has_access("read")


def _split_pos_bus_key(key) -> tuple[str, str, str, str]:
    model, record_id, audience, revision = (key.rsplit(".", 3) + ["", "", ""])[:4]
    return model, record_id, audience, revision


POS_CHANNEL = register_channel_scope(
    "pos.bus",
    purpose="one point-of-sale record's notifications to one audience of its "
    "devices: the till, its customer display, its order-tracking screen",
    lifetime="until the record's access token is rotated",
    holder=_holds_pos_channel,
)


def _new_access_token() -> str:
    return str(uuid.uuid4())


def _describe_payload(message):
    return sorted(message) if isinstance(message, dict) else type(message).__name__


class MixinPosBus(models.AbstractModel):
    _name = "mixin.pos.bus"
    _description = "Bus Mixin"

    access_token = fields.Char(
        string="Security Token",
        default=lambda self: _new_access_token(),
        copy=False,
    )

    def _pos_bus_get_or_create_token(self) -> str:
        self.check_singleton()
        if self.access_token:
            return self.access_token
        token = _new_access_token()
        _debug.lifecycle("access_token_minted", records=self)
        # a cashier opens the channel of a pos.config it may not write
        self.sudo().access_token = token
        return token

    def _pos_bus_rotate_token(self) -> None:
        for record in self:
            _debug.lifecycle("access_token_rotated", record=record)
            record.access_token = _new_access_token()

    def _pos_bus_audience_generation(self, audience) -> int:
        """How many times ``audience``'s link and channel were revoked alone,
        beside the record's token: 0 for an audience only the token revokes."""
        return 0

    def _pos_bus_key(self, audience) -> str:
        token = self._pos_bus_get_or_create_token()
        generation = self._pos_bus_audience_generation(audience)
        revision = token_revision(f"{token}:{generation}" if generation else token)
        return f"{self._name}.{self.id}.{audience}.{revision}"

    def _pos_bus_revoke(self, audience, generation_field) -> None:
        """Revoke ``audience``'s link and channel: its open screens are told
        to reload, and their link then opens nothing."""
        for record in self:
            record._notify("LINK_REVOKED", {}, audience=audience)
            _debug.lifecycle("audience_revoked", record=record, audience=audience)
            record[generation_field] += 1

    def _pos_bus_channel(self, audience="till") -> str:
        """The name the devices of ``audience`` subscribe with; it also
        prefixes the notification types they listen to."""
        self.check_singleton()
        return channel_capability(self.env, POS_CHANNEL, self._pos_bus_key(audience))

    def _notify(self, *notifications, audience="till") -> None:
        self.check_singleton()
        key = self._pos_bus_key(audience)
        channel = channel_capability(self.env, POS_CHANNEL, key)
        target = channel_target(self.env, POS_CHANNEL, key)
        if isinstance(notifications[0], str):
            if len(notifications) != 2:
                raise ValueError(
                    "If you want to send a single notification, you must provide a name: str and a message: any"
                )
            notifications = [notifications]
        for name, message in notifications:
            if _debug.pipeline.enabled:
                _debug.pipeline(
                    "bus_notify",
                    name=name,
                    records=self,
                    audience=audience,
                    payload=_describe_payload(message),
                )
            self.env["bus.bus"]._sendone(
                target,
                f"{channel}-{name}",
                message,
            )
