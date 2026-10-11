import logging

from werkzeug.wrappers import Response

from odoo.http import Controller, request, route

from odoo.addons.integration_twilio.models.integration_twilio_config import EMPTY_TWIML

_logger = logging.getLogger(__name__)

TWILIO_TO_SMS_STATE_ERRORS = {
    "failed": "error",
    "undelivered": "error",
}
TWILIO_TO_SMS_STATE = {
    "queued": "outgoing",
    "sending": "process",
    "sent": "pending",
    "delivered": "sent",
    "accepted": "outgoing",
    "scheduled": "outgoing",
    "canceled": "canceled",
    **TWILIO_TO_SMS_STATE_ERRORS,
}


class TwilioController(Controller):
    @route(
        [
            "/integration_twilio/sms/status/<string:uuid>",
            "/sms_twilio/status/<string:uuid>",
        ],
        type="http",
        auth="receiver",
        receiver="sms.sms:_receiver_for_twilio_status",
        receiver_event="twilio_sms_status",
        receiver_refusal="integration.twilio.config:_prepare_twilio_refusal_response",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def update_sms_status(
        self,
        uuid: str,
        MessageStatus: str | None = None,
        SmsStatus: str | None = None,
        ErrorCode: str | None = None,
        ErrorMessage: str | None = None,
        **kwargs,
    ):
        status = MessageStatus or SmsStatus
        if status not in TWILIO_TO_SMS_STATE:
            _logger.info("Twilio SMS: status %r left as it was", status)
            return ""

        subject_sudo = request.admission.subject
        is_tracker = subject_sudo._name == "sms.tracker"
        tracker_sudo = subject_sudo if is_tracker else subject_sudo.sms_tracker_id
        if not tracker_sudo:
            _logger.warning(
                "Twilio SMS: status callback for no tracker (uuid %s)", uuid
            )
            return ""

        if status in TWILIO_TO_SMS_STATE_ERRORS:
            tracker_sudo._action_update_from_twilio_error(
                status, ErrorCode, ErrorMessage
            )
        else:
            tracker_sudo._action_update_from_sms_state(TWILIO_TO_SMS_STATE[status])

        if not is_tracker:
            subject_sudo.to_delete = True
        return ""

    @route(
        "/integration_twilio/sms/inbound/<string:twilio_sid>",
        type="http",
        auth="receiver",
        receiver="integration.twilio.number:_receiver_for_inbound_sms",
        receiver_event="twilio_sms_inbound",
        receiver_refusal="integration.twilio.config:_prepare_twilio_refusal_response",
        methods=["POST"],
        csrf=False,
        typed=True,
    )
    def receive_sms(self, twilio_sid: str, **params):
        request.admission.subject._receive_sms(request.httprequest.form)
        return Response(EMPTY_TWIML, status=200, content_type="text/xml")
