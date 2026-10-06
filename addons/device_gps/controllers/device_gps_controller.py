import logging
import time

from psycopg import OperationalError
from werkzeug.wrappers import Response

from odoo import http
from odoo.http import request
from odoo.libs.json import dumps as json_dumps

from ..models.device_device import TRACKER_ACK, TRACKER_NACK

_logger = logging.getLogger(__name__)


class DeviceGpsController(http.Controller):
    @staticmethod
    def _answer(byte):
        return Response(byte, status=200, mimetype="application/octet-stream")

    @http.route(
        "/remote/gps/webhook",
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_tracker",
        receiver_event="gps_fix",
        receiver_refusal="device.device:_prepare_tracker_refusal_response",
        methods=["POST"],
        csrf=False,  # auth="receiver": the device's inbound gate authenticates the tracker
        save_session=False,
        typed=True,
    )
    def remote_gps_webhook(self, **kwargs) -> Response:
        return self._process_webhook()

    @http.route(
        "/device/v1/enrollments/<string:enrollment_key>/channels/<string:channel_key>/gps",
        type="http",
        auth="receiver",
        receiver="device.channel:_receiver_for_gps",
        receiver_event="gps_fix",
        receiver_refusal="device.device:_prepare_tracker_refusal_response",
        methods=["POST"],
        csrf=False,
        save_session=False,
        typed=True,
    )
    def channel_gps_webhook(self, enrollment_key: str, channel_key: str) -> Response:
        # CSRF exemption: enrollment credentials authenticate this machine route.
        return self._process_webhook()

    def _process_webhook(self) -> Response:
        start_time = time.perf_counter()
        admission = request.admission
        device = admission.subject
        payload = admission.extra["payload"]
        json_data = admission.extra["json_data"]
        remote_addr = admission.remote_addr
        processing_stats = {
            "validation_time": 0.0,
            "db_operation_time": 0.0,
            "quality_checks_passed": 0,
            "quality_checks_failed": 0,
        }
        processor = request.env["device.gps.data.processor"].sudo()

        validation_start = time.perf_counter()
        is_valid, message, device, vals = processor._process_gps_data(
            payload,
            processing_stats,
            device=device,
            channel=admission.extra.get("channel"),
        )
        processing_stats["validation_time"] = time.perf_counter() - validation_start

        if not is_valid:
            admission.settle(f"Validation failed: {message}")
            self._log_webhook_result(
                start_time,
                remote_addr,
                admission.subject.id,
                f"Validation failed: {message}",
                processing_stats,
                vals,
                is_success=False,
            )
            return self._answer(TRACKER_NACK)

        try:
            vals["raw_payload"] = json_dumps(json_data)
        except TypeError, ValueError:
            vals["raw_payload"] = str(json_data)

        vals["source"] = "webhook"
        db_start_time = time.perf_counter()

        try:
            with request.env.cr.savepoint():
                request.env["device.data.log.gps"].sudo().create_gps_log(vals)

            processing_stats["db_operation_time"] = time.perf_counter() - db_start_time
            admission.settle()
            self._log_webhook_result(
                start_time,
                remote_addr,
                admission.subject.id,
                "GPS log created successfully",
                processing_stats,
                vals,
                is_success=True,
            )
            return self._answer(TRACKER_ACK)

        except OperationalError:
            raise

        except Exception as db_error:
            processing_stats["db_operation_time"] = time.perf_counter() - db_start_time
            error_msg = f"Database transaction failed: {db_error!s}"
            _logger.exception("Database transaction failed")
            admission.settle(error_msg)
            self._log_webhook_result(
                start_time,
                remote_addr,
                admission.subject.id,
                error_msg,
                processing_stats,
                vals,
                is_success=False,
            )
            return self._answer(TRACKER_NACK)

    def _log_webhook_result(
        self,
        start_time: float,
        remote_addr: str,
        device_id: int,
        message: str,
        processing_stats: dict,
        vals: dict | None = None,
        is_success: bool = True,
    ):
        # Every tracker push reaches this, and the line it feeds is DEBUG,
        # which is off by default: build nothing until somebody is listening.
        if not _logger.isEnabledFor(logging.DEBUG):
            return

        total_duration = time.perf_counter() - start_time

        quality_metrics = {}
        if vals:
            quality_metrics = {
                "satellites": vals.get("satellites", "N/A"),
                "speed": vals.get("speed", "N/A"),
                "fuel_level": vals.get("fuel_level", "N/A"),
                "engine_temp": vals.get("engine_temperature", "N/A"),
                "coordinates": f"({vals.get('latitude', 'N/A')}, {vals.get('longitude', 'N/A')})",
                "timestamp": vals.get("timestamp", "N/A"),
                "device_id": vals.get("device_id", "N/A"),
            }

        status = "SUCCESS" if is_success else "FAILURE"

        _logger.debug(
            "GPS_WEBHOOK_%s device=%s ip=%s duration=%.3fs validation=%.3fs db=%.3fs "
            "quality_passed=%d quality_failed=%d message='%s' metrics=%s",
            status,
            device_id,
            remote_addr,
            total_duration,
            processing_stats.get("validation_time", 0),
            processing_stats.get("db_operation_time", 0),
            processing_stats.get("quality_checks_passed", 0),
            processing_stats.get("quality_checks_failed", 0),
            message,
            quality_metrics,
        )
