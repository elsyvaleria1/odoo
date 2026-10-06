from odoo import http
from odoo.http import request

from odoo.addons.device_phone_call.controllers.main import DevicePhoneCallController


class DeviceVoipController(DevicePhoneCallController):
    @http.route(
        [
            "/remote/device/<string:identifier>/softphone",
            "/remote/mobile/<string:identifier>/softphone",
        ],
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_identifier",
        receiver_refusal="device.device:_prepare_companion_refusal_response",
        receiver_event="softphone_settings",
        methods=["GET"],
        save_session=False,
        typed=True,
    )
    def softphone_settings(self, identifier: str, **kwargs):
        admission = request.admission
        settings = admission.subject._softphone_settings()
        if not settings:
            admission.settle("the phone user has no extension")
            return self._error_response(
                "no_extension", "The phone's user has no extension", 404
            )
        admission.settle()
        return self._json_response({"status": "success", "sip": settings})
