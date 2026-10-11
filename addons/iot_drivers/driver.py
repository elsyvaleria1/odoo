import logging
from threading import Event, Thread

from odoo.libs.lru import LRU

from odoo.addons.iot_drivers.event_manager import event_manager
from odoo.addons.iot_drivers.main import drivers, iot_devices
from odoo.addons.iot_drivers.tools.helpers import toggleable

_logger = logging.getLogger(__name__)


class Driver(Thread):
    """Hook to register the driver into the drivers list"""

    connection_type = ""
    priority = 0

    def __init__(self, identifier, device) -> None:
        super().__init__(daemon=True)
        self.dev = device
        self.device_identifier = identifier
        self.device_name = ""
        self.device_connection = ""
        self.device_type = ""
        self.device_manufacturer = ""
        self.data = {"value": "", "result": ""}
        self._actions = {}
        self._stopped = Event()
        self._recent_action_ids = LRU(256)

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        if cls not in drivers:
            drivers.append(cls)

    @classmethod
    def supported(cls, device):
        return False

    @toggleable
    def action(self, data) -> None:
        action = data.get("action", "")
        action_unique_id = data.get("action_unique_id")
        if action_unique_id:
            if action_unique_id in self._recent_action_ids:
                _logger.warning(
                    "Duplicate action %s id %s received, ignoring",
                    action,
                    action_unique_id,
                )
                return
            self._recent_action_ids[action_unique_id] = action_unique_id

        self.data["owner"] = data.get("session_id")

        base_response = {"action_args": {**data}, "session_id": data.get("session_id")}
        try:
            response = {
                "status": "success",
                "result": self._actions[action](data),
                **base_response,
            }
        except Exception as e:
            if action_unique_id:
                self._recent_action_ids.pop(action_unique_id, None)
            _logger.exception(
                "Error while executing action %s with params %s", action, data
            )
            response = {"status": "error", "result": str(e), **base_response}

        if self.device_type not in ["printer", "payment"]:
            event_manager.device_changed(self, response)

    def disconnect(self):
        self._stopped.set()
        del iot_devices[self.device_identifier]
