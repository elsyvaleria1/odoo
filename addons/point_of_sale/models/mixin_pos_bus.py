import uuid

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


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

    def _notify(self, *notifications, private=True) -> None:
        self.check_singleton()
        token = self._pos_bus_get_or_create_token()
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
                    private=private,
                    payload=_describe_payload(message),
                )
            self.env["bus.bus"]._sendone(
                token,
                f"{token}-{name}" if private else name,
                message,
            )
