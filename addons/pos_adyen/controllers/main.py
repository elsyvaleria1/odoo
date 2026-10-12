import logging
import pprint
from urllib.parse import parse_qs

from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class PosAdyenController(http.Controller):
    @http.route(
        "/pos_adyen/notification",
        type="http",
        methods=["POST"],
        auth="receiver",
        receiver="pos.payment.method:_receiver_for_adyen_terminal",
        receiver_event="adyen_terminal",
        csrf=False,
        save_session=False,
        typed=True,
    )
    def notification(self):
        adyen_pm_sudo = request.admission.subject
        data = request.admission.extra["data"]
        adyen_additional_response = data["SaleToPOIResponse"]["PaymentResponse"][
            "Response"
        ]["AdditionalResponse"]
        pos_hmac = PosAdyenController._get_additional_data_from_unparsed(
            adyen_additional_response, "metadata.pos_hmac"
        )
        pos_hmac_metadata_raw = "metadata.pos_hmac=" + pos_hmac
        data["SaleToPOIResponse"]["PaymentResponse"]["Response"][
            "AdditionalResponse"
        ] = adyen_additional_response.replace("&" + pos_hmac_metadata_raw, "").replace(
            pos_hmac_metadata_raw, ""
        )
        _logger.info("notification received from adyen:\n%s", pprint.pformat(data))
        pending = adyen_pm_sudo._adyen_consume_pending_request(data)
        if pending is None:
            raise Forbidden
        adyen_pm_sudo._adyen_record_notification(data, pending)
        return request.prepare_json_response("[accepted]")

    @staticmethod
    def _get_additional_data_from_unparsed(adyen_additional_response, data_key):
        parsed_adyen_additional_response = parse_qs(adyen_additional_response)
        return PosAdyenController._get_additional_data_from_parsed(
            parsed_adyen_additional_response, data_key
        )

    @staticmethod
    def _get_additional_data_from_parsed(parsed_adyen_additional_response, data_key):
        data_value = parsed_adyen_additional_response.get(data_key)
        return data_value[0] if data_value and len(data_value) == 1 else None
