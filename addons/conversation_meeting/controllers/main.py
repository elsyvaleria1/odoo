import logging
import math

from odoo import http
from odoo.db.errors import PG_RETRY_EXCEPTIONS
from odoo.exceptions import UserError
from odoo.http import request

_logger = logging.getLogger(__name__)


class ConversationMeetingController(http.Controller):
    def _room_conversation(self, device, conversation_id):
        return request.env["conversation.conversation"].search(
            [
                ("id", "=", conversation_id),
                ("company_id", "=", device.company_id.id),
            ],
            limit=1,
        )

    def _refuse(self, admission, code, message, status):
        admission.settle(message)
        return request.prepare_json_response(
            {"error": code, "message": message}, status=status
        )

    @http.route(
        "/conversation/<string:identifier>/<int:conversation_id>/audio",
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_meeting_room",
        receiver_event="meeting_audio",
        methods=["POST"],
        csrf=False,
        save_session=False,
        typed=True,
    )
    def room_push_audio(self, identifier: str, conversation_id: int, **kwargs):
        result = request.admission
        device = result.subject
        payload = result.json()
        Record = request.env["conversation.conversation"]
        try:
            audio = Record._live_decode(payload)
        except UserError:
            return self._refuse(
                result, "bad_audio", "Recording is not valid base64", 400
            )
        if not audio:
            return self._refuse(result, "no_audio", "No recording in payload", 400)
        conversation = self._room_conversation(device, conversation_id)
        if not conversation:
            return self._refuse(
                result, "not_found", "Unknown conversation for this device", 404
            )
        try:
            with request.env.cr.savepoint():
                conversation._file_room_recording(
                    audio,
                    payload.get("file_name") or "room.wav",
                    payload.get("mimetype") or "audio/wav",
                    replace=bool(payload.get("replace")),
                )
                device._touch_last_seen()
        except UserError as error:
            return self._refuse(result, "audio_exists", str(error), 409)
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception:
            _logger.exception("Failed to store room audio")
            return self._refuse(
                result, "processing_error", "Failed to store the recording", 500
            )
        result.settle()
        return request.prepare_json_response(
            {
                "status": "success",
                "conversation_id": conversation.id,
                "state": conversation.state,
            }
        )

    @http.route(
        "/conversation/<string:identifier>/<int:conversation_id>/chunk",
        type="http",
        auth="receiver",
        receiver="device.device:_receiver_for_meeting_room",
        receiver_event="meeting_chunk",
        methods=["POST"],
        csrf=False,
        save_session=False,
        typed=True,
    )
    def room_push_chunk(self, identifier: str, conversation_id: int, **kwargs):
        result = request.admission
        device = result.subject
        payload = result.json()
        Record = request.env["conversation.conversation"]
        try:
            audio = Record._live_decode(payload)
            start_s = float(payload.get("start_s") or 0.0)
            duration_s = float(payload.get("duration_s") or 0.0)
            if not (math.isfinite(start_s) and math.isfinite(duration_s)):
                raise ValueError("offsets must be finite")
        except TypeError, ValueError, UserError:
            return self._refuse(result, "bad_chunk", "Chunk payload is not valid", 400)
        if not audio:
            return self._refuse(result, "no_audio", "No chunk in payload", 400)
        conversation = self._room_conversation(device, conversation_id)
        if not conversation:
            return self._refuse(
                result, "not_found", "Unknown conversation for this device", 404
            )
        try:
            with request.env.cr.savepoint():
                conversation._ingest_live_chunk(
                    audio,
                    start_s,
                    duration_s=duration_s,
                    mimetype=payload.get("mimetype") or "audio/wav",
                )
                device._touch_last_seen()
        except UserError as error:
            return self._refuse(result, "not_accepted", str(error), 422)
        except PG_RETRY_EXCEPTIONS:
            raise
        except Exception:
            _logger.exception("Failed to process live chunk")
            return self._refuse(
                result, "processing_error", "Failed to process the chunk", 500
            )
        result.settle()
        return request.prepare_json_response(
            {
                "status": "success",
                "conversation_id": conversation.id,
                "chunks": conversation.live_chunk_count,
            }
        )
