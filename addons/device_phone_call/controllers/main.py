import logging

from odoo import http
from odoo.http import request

from ..models.device_device import COMPANION_SERVICE

_logger = logging.getLogger(__name__)


class DevicePhoneCallController(http.Controller):
    """What a company handset and a phone system report of their calls, on
    the companion app's wire contract: a reply names its service, and a batch
    answers what it stored, what it already had and what it could not use."""

    @http.route(
        [
            "/remote/device/<string:identifier>/calllog",
            "/remote/mobile/<string:identifier>/calllog",
        ],
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_identifier",
        receiver_refusal="device.device:_prepare_companion_refusal_response",
        receiver_event="mobile_calllog",
        methods=["POST"],
        csrf=False,  # auth="receiver": the device's inbound gate authenticates the phone
        save_session=False,
        typed=True,
    )
    def push_calllog(self, identifier: str, **kwargs):
        admission = request.admission
        device = admission.subject
        calls = self._extract_items(self._payload(admission), "calls")
        if not calls:
            admission.settle("no call entries in payload")
            return self._error_response("no_calls", "No call entries in payload", 400)

        try:
            with request.env.cr.savepoint():
                ingest = (
                    request.env["phone.call"].sudo().ingest_from_device(device, calls)
                )
                device.sudo()._touch_last_seen()
        except Exception as error:
            _logger.exception("Failed to store mobile call log")
            admission.settle(str(error))
            return self._error_response(
                "processing_error", "Failed to store call log", 500
            )

        accepted = len(ingest.created)
        if accepted or ingest.duplicates:
            admission.settle()
        else:
            admission.settle("no usable call entry in the batch")
        return self._json_response(
            {
                "status": "success",
                "accepted": accepted,
                "duplicates": ingest.duplicates,
                "skipped": len(calls) - accepted - ingest.duplicates,
                "skipped_indexes": list(ingest.skipped_indexes),
                "matched": len(ingest.created.filtered("partner_id")),
                "device_name": device.name,
                "max_payload_bytes": device.max_payload_size,
            },
            status=self._ingest_status(accepted, ingest.duplicates),
        )

    @http.route(
        [
            "/remote/device/<string:identifier>/recording",
            "/remote/mobile/<string:identifier>/recording",
        ],
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_identifier",
        receiver_refusal="device.device:_prepare_companion_refusal_response",
        receiver_event="mobile_recording",
        methods=["POST"],
        csrf=False,  # auth="receiver": the device's inbound gate authenticates the phone
        save_session=False,
        typed=True,
    )
    def push_recording(self, identifier: str, **kwargs):
        admission = request.admission
        device = admission.subject
        payload = self._payload(admission)
        if not isinstance(payload, dict) or not (
            payload.get("audio") or payload.get("audio_b64")
        ):
            admission.settle("no recording in payload")
            return self._error_response("no_audio", "No recording in payload", 400)

        try:
            with request.env.cr.savepoint():
                ingest = (
                    request.env["phone.call"]
                    .sudo()
                    .store_device_recording(device, payload)
                )
                device.sudo()._touch_last_seen()
        except ValueError as error:
            admission.settle(str(error))
            return self._error_response(
                "bad_recording", "Invalid recording payload", 400
            )
        except Exception as error:
            _logger.exception("Failed to store mobile recording")
            admission.settle(str(error))
            return self._error_response(
                "processing_error", "Failed to store recording", 500
            )

        admission.settle()
        return self._json_response(
            {
                "status": "success",
                "recording_id": ingest.attachment.id,
                "call_id": ingest.call.id,
                "matched": ingest.matched,
                "duplicates": int(ingest.duplicate),
                "device_name": device.name,
                "max_payload_bytes": device.max_payload_size,
            }
        )

    @staticmethod
    def _payload(admission):
        payload = admission.payload
        if payload is None:
            admission.refuse(400, "the request body is not JSON", "invalid_json")
        return payload

    def _json_response(self, data, status=200):
        return request.prepare_json_response(
            {"service": COMPANION_SERVICE, **data}, status=status
        )

    def _error_response(self, error_code, message, status):
        return self._json_response(
            {"error": error_code, "message": message}, status=status
        )

    @staticmethod
    def _ingest_status(accepted, duplicates):
        return 200 if accepted or duplicates else 422

    @staticmethod
    def _extract_items(payload, list_key):
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            items = payload.get(list_key)
            if isinstance(items, list):
                return items
            return [payload]
        return []
