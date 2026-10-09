import logging

from odoo import http
from odoo.http import request

from odoo.addons.device_phone_call.controllers.main import DevicePhoneCallController

_logger = logging.getLogger(__name__)


class DeviceMobileController(DevicePhoneCallController):
    @http.route(
        "/remote/mobile/<string:identifier>/location",
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_identifier",
        receiver_refusal="device.device:_prepare_companion_refusal_response",
        receiver_event="mobile_location",
        methods=["POST"],
        csrf=False,  # auth="receiver": the device's inbound gate authenticates the phone
        save_session=False,
        typed=True,
    )
    def mobile_push_location(self, identifier: str, **kwargs):
        admission = request.admission
        device = admission.subject
        points = self._extract_items(self._payload(admission), "points")
        if not points:
            admission.settle("no GPS fixes in payload")
            return self._error_response("no_points", "No GPS fixes in payload", 400)

        try:
            with request.env.cr.savepoint():
                ingest = request.env["device.data.log.gps"].ingest_from_mobile(
                    device, points
                )
                device._touch_last_seen()
        except Exception as error:
            _logger.exception("Failed to store mobile GPS fixes")
            admission.settle(str(error))
            return self._error_response(
                "processing_error", "Failed to store GPS fixes", 500
            )

        accepted = len(ingest.created)
        if accepted or ingest.duplicates:
            admission.settle()
        else:
            admission.settle("no usable GPS fix in the batch")
        return self._json_response(
            {
                "status": "success",
                "accepted": accepted,
                "duplicates": ingest.duplicates,
                "skipped": len(points) - accepted - ingest.duplicates,
                "skipped_indexes": list(ingest.skipped_indexes),
                "device_name": device.name,
                "max_payload_bytes": device.max_payload_size,
            },
            status=self._ingest_status(accepted, ingest.duplicates),
        )
