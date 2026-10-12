import time
from threading import Event

from odoo.http import request

from odoo.addons.iot_drivers.tools import helpers
from odoo.addons.iot_drivers.webrtc_client import webrtc_client
from odoo.addons.iot_drivers.websocket_client import send_to_controller


class EventManager:
    def __init__(self) -> None:
        self.events = []
        self.sessions = {}

    def _remove_expired_sessions(self, ttl=70) -> None:
        self.sessions = {
            session: self.sessions[session]
            for session in self.sessions
            if self.sessions[session]["time_request"] + ttl < time.time()
        }

    def add_request(self, listener):
        session_id = listener["session_id"]
        session = {
            "session_id": session_id,
            "devices": listener["devices"],
            "event": Event(),
            "result": {},
            "time_request": time.time(),
        }
        self._remove_expired_sessions()

        self.sessions[session_id] = session
        return session

    def device_changed(self, device, data=None) -> None:
        data = data or (request.params.get("data", {}) if request else {})

        event = {
            **device.data,
            "device_identifier": device.device_identifier,
            "time": time.time(),
            **data,
        }
        send_to_controller(
            {
                **event,
                "iot_box_identifier": helpers.get_identifier(),
            }
        )
        if webrtc_client:
            webrtc_client.send(event)
        self.events.append(event)
        for session in self.sessions:
            session_devices = self.sessions[session]["devices"]
            if (
                any(
                    d in [device.device_identifier, device.device_type]
                    for d in session_devices
                )
                and not self.sessions[session]["event"].is_set()
            ):
                if device.device_type in session_devices:
                    event["device_identifier"] = device.device_type
                self.sessions[session]["result"] = event
                self.sessions[session]["event"].set()


event_manager = EventManager()
