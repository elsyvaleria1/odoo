import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosVivaComController(http.Controller):
    @http.route(
        "/pos_viva_com/notification",
        type="http",
        auth="receiver",
        receiver="pos.payment.method:_receiver_for_viva_com_notification",
        receiver_event="viva_com_terminal",
        csrf=False,
        readonly=False,
        typed=True,
    )
    def notification(self, company_id: int, token: str):
        _logger.info("notification received from Viva.com")
        admission = request.admission
        payment_method_sudo = admission.subject
        if request.httprequest.data:
            data = admission.json()
            event_type = data.get("EventTypeId")
            if event_type != 1796:
                _logger.warning(
                    'received a message with an unknown event type "%s". See https://developer.viva.com/webhooks-for-payments/#webhook-events.',
                    event_type,
                )
            else:
                self._notify_payment_created(admission, data.get("EventData"))
        return request.prepare_json_response(
            {"Key": payment_method_sudo.viva_com_webhook_verification_key}
        )

    @staticmethod
    def _notify_payment_created(admission, data_webhook):
        if not isinstance(data_webhook, dict):
            admission.refuse(400, "EventData is not a JSON object", "invalid_json")
        terminal_id = data_webhook.get("TerminalId")
        terminal_method_sudo = admission.subject._get_viva_com_terminal_method(
            terminal_id
        )
        if not terminal_method_sudo:
            _logger.error(
                "received a message for a terminal not registered in Odoo: %s",
                terminal_id,
            )
            return
        merchant_trns = data_webhook.get("MerchantTrns")
        if not merchant_trns:
            return
        sessions = terminal_method_sudo._get_viva_com_merchant_trns_sessions(
            merchant_trns
        )
        if not sessions:
            _logger.warning(
                "Viva.com notified terminal %s of a sale with merchant reference %r,"
                " which names no POS session.",
                terminal_method_sudo.viva_com_terminal_id,
                merchant_trns,
            )
            return
        terminal_method_sudo._notify_session_status(*sessions, data_webhook)
