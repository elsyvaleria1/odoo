from typing import TYPE_CHECKING, Literal, Protocol, Self, TypedDict

from odoo.exceptions import ValidationError

if TYPE_CHECKING:
    from odoo.api import Environment
    from odoo.orm.models import BaseModel
    from odoo.orm.primitives import IdType


class GpsDeviceOwner(Protocol):
    env: Environment
    gps_device_id: BaseModel

    def check_singleton(self) -> Self: ...


class GpsDeviceAction(TypedDict):
    name: str
    type: Literal["ir.actions.act_window"]
    res_model: Literal["device.device"]
    res_id: IdType | Literal[False]
    view_mode: Literal["form"]
    target: Literal["new"]


def prepare_gps_device_action(owner: GpsDeviceOwner) -> GpsDeviceAction:
    """Build device navigation from a carrier; legacy name-only carriers work."""
    owner.check_singleton()
    if not owner.gps_device_id:
        raise ValidationError(owner.env._("No GPS device assigned to this resource"))
    label = getattr(owner, "display_name", None) or getattr(owner, "name", "")
    return {
        "name": owner.env._("GPS Device: %s") % label,
        "type": "ir.actions.act_window",
        "res_model": "device.device",
        "res_id": owner.gps_device_id.id,
        "view_mode": "form",
        "target": "new",
    }
