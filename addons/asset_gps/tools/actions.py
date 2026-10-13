
from typing import Protocol

from odoo.addons.device_gps.tools.actions import (
    GpsDeviceAction,
    prepare_gps_device_action,
)
from odoo.addons.device_gps.tools.actions import (
    GpsDeviceOwner as GpsNavigationOwner,
)


class GpsDeviceOwner(GpsNavigationOwner, Protocol):
    name: str


__all__ = ["GpsDeviceAction", "GpsDeviceOwner", "prepare_gps_device_action"]
