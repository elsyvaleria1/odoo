from odoo import http
from odoo.http import request


class DeviceChannelController(http.Controller):
    @http.route(
        "/device/v1/enrollments/<string:enrollment_key>/channels/<string:channel_key>/status",
        type="http",
        auth="receiver",
        receiver="device.channel:_receiver_for_route",
        receiver_event="channel_status",
        methods=["GET"],
        save_session=False,
        typed=True,
    )
    def channel_status(self, enrollment_key: str, channel_key: str):
        channel = request.admission.subject
        request.admission.settle()
        return request.prepare_json_response(
            {"status": "active", "purpose": channel.purpose}
        )
