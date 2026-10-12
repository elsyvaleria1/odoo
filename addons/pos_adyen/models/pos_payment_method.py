import logging
import pprint
import random
import re
from urllib.parse import parse_qs, urlencode

from odoo import api, fields, models
from odoo.exceptions import AccessDenied, UserError, ValidationError
from odoo.http import request
from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads
from odoo.tools import consteq, hmac, register_signed_scope

from odoo.addons.integration.tools.admission import Acknowledged, json_get

_logger = logging.getLogger(__name__)

UNPREDICTABLE_ADYEN_DATA = object()
POS_HMAC_METADATA = re.compile(r"(metadata\.pos_hmac=)[^&]*")


def redact_pos_hmac(data):
    if isinstance(data, dict):
        return {key: redact_pos_hmac(value) for key, value in data.items()}
    if isinstance(data, list):
        return [redact_pos_hmac(value) for value in data]
    if isinstance(data, str):
        return POS_HMAC_METADATA.sub(r"\1<redacted>", data)
    return data


PAYMENT_SCOPE = register_signed_scope(
    "pos_adyen_payment",
    purpose="bind an Adyen terminal notification to the sale, service, terminal "
    "and transaction ids the POS sent it",
    lifetime="undated: one payment round trip",
)


class PosPaymentMethod(models.Model):
    _name = "pos.payment.method"
    _inherit = ["pos.payment.method", "mixin.integration.connected"]

    @api.model
    def _receiver_for_adyen_terminal(self, **path_args) -> tuple:
        try:
            data = request.get_json_data()
        except ValueError:
            data = None
        if not json_get(data, "SaleToPOIResponse"):
            raise Acknowledged.json(None)
        msg_header = json_get(data, "SaleToPOIResponse", "MessageHeader")
        if (
            not isinstance(msg_header, dict)
            or msg_header.get("ProtocolVersion") != "3.0"
            or msg_header.get("MessageClass") != "Service"
            or msg_header.get("MessageType") != "Response"
            or msg_header.get("MessageCategory") != "Payment"
            or not isinstance(msg_header.get("POIID"), str)
            or not msg_header["POIID"]
        ):
            _logger.warning("Received an unexpected Adyen notification")
            raise Acknowledged.json(None)
        terminal_identifier = msg_header["POIID"]
        method = self.sudo().search(
            [("adyen_terminal_identifier", "=", terminal_identifier)], limit=1
        )
        if not method:
            _logger.warning(
                "Received an Adyen event notification for a terminal not registered "
                "in Odoo: %s",
                terminal_identifier,
            )
            request.env["integration.exchange"]._record_unknown_caller(
                self._name,
                f"Adyen terminal {terminal_identifier}"[:64],
                request.httprequest.remote_addr,
                user_agent=request.httprequest.headers.get("User-Agent"),
                status_code=200,
            )
            raise Acknowledged.json(None)
        return method, {"data": data}

    def _inbound_gate_owner(self):
        return self, f"{self.name} notifications", None

    @staticmethod
    def _adyen_additional_data(adyen_additional_response, data_key):
        values = parse_qs(adyen_additional_response).get(data_key)
        return values[0] if values and len(values) == 1 else None

    def _is_inbound_request_authentic(self, headers, body) -> bool:
        if self.use_payment_terminal != "adyen":
            return super()._is_inbound_request_authentic(headers, body)
        data = request.get_json_data()
        try:
            response = data["SaleToPOIResponse"]["PaymentResponse"]
            msg_header = data["SaleToPOIResponse"]["MessageHeader"]
            pos_hmac = self._adyen_additional_data(
                response["Response"]["AdditionalResponse"], "metadata.pos_hmac"
            )
            expected = self._get_hmac(
                msg_header["SaleID"],
                msg_header["ServiceID"],
                msg_header["POIID"],
                response["SaleData"]["SaleTransactionID"]["TransactionID"],
            )
        except KeyError, TypeError:
            return False
        return (
            bool(pos_hmac)
            and consteq(pos_hmac, expected)
            and self._adyen_pending_request_for(data) is not None
        )

    def _adyen_pending_request_for(self, data):
        pending_json = self.adyen_pending_request
        if not pending_json:
            return None
        pending = json_loads(pending_json)
        try:
            msg_header = data["SaleToPOIResponse"]["MessageHeader"]
            response = data["SaleToPOIResponse"]["PaymentResponse"]
            notified = (
                msg_header["SaleID"],
                msg_header["ServiceID"],
                msg_header["POIID"],
                response["SaleData"]["SaleTransactionID"]["TransactionID"],
            )
            if notified != (
                pending["sale_id"],
                pending["service_id"],
                self.adyen_terminal_identifier,
                pending["transaction_id"],
            ):
                return None
            if response["Response"].get(
                "Result"
            ) == "Success" and not self._adyen_amounts_match(
                response["PaymentResult"]["AmountsResp"], pending
            ):
                return None
        except KeyError, TypeError, AttributeError:
            return None
        return pending

    def _adyen_amounts_match(self, amounts, pending) -> bool:
        authorized = amounts["AuthorizedAmount"]
        tip = amounts.get("TipAmount") or 0
        if amounts.get("Currency", pending["currency"]) != pending["currency"]:
            return False
        if not all(
            isinstance(value, int | float) and not isinstance(value, bool)
            for value in (authorized, tip)
        ):
            return False
        currency = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search([("name", "=", pending["currency"])], limit=1)
        )
        return bool(currency) and not currency.compare_amounts(
            authorized - tip, pending["amount"]
        )

    def _adyen_consume_pending_request(self, data):
        pending = self._adyen_pending_request_for(data)
        if pending is not None:
            self.adyen_pending_request = False
        return pending

    def _adyen_record_notification(self, data, pending) -> None:
        result = data["SaleToPOIResponse"]["PaymentResponse"]["Response"].get("Result")
        state = "pending" if result == "Success" else "final"
        self.write(
            {
                "adyen_latest_response": json_dumps(data),
                "adyen_confirmed_request": json_dumps(pending),
                "adyen_confirmation_state": state,
            }
        )
        if state == "pending":
            self.env.ref("pos_adyen.ir_cron_confirm_adyen_payment")._trigger()
        else:
            self._adyen_settle(data, pending, state)

    @api.model
    def _cron_confirm_adyen_payments(self) -> None:
        for method in self.search([("adyen_confirmation_state", "=", "pending")]):
            method._adyen_confirm_pending_payment()

    def _adyen_confirm_pending_payment(self) -> None:
        self.check_singleton()
        self.lock_for_update(wait=True)
        self.invalidate_recordset(
            [
                "adyen_confirmation_state",
                "adyen_latest_response",
                "adyen_confirmed_request",
            ]
        )
        if self.adyen_confirmation_state != "pending":
            return
        data = json_loads(self.adyen_latest_response)
        pending = json_loads(self.adyen_confirmed_request)
        state = self._adyen_transaction_status(data, pending)
        if state == "failed":
            data = self._adyen_reported_failed(data)
        self.write(
            {
                "adyen_latest_response": json_dumps(data),
                "adyen_confirmation_state": state,
            }
        )
        self._adyen_settle(data, pending, state)

    def _adyen_transaction_status(self, data, pending) -> str:
        status_request = {
            "SaleToPOIRequest": {
                "MessageHeader": {
                    "ProtocolVersion": "3.0",
                    "MessageClass": "Service",
                    "MessageCategory": "TransactionStatus",
                    "MessageType": "Request",
                    "SaleID": pending["sale_id"],
                    "ServiceID": str(random.randrange(10**9, 10**10)),
                    "POIID": self.adyen_terminal_identifier,
                },
                "TransactionStatusRequest": {
                    "MessageReference": {
                        "MessageCategory": "Payment",
                        "SaleID": pending["sale_id"],
                        "ServiceID": pending["service_id"],
                    },
                },
            },
        }
        try:
            reply = self._proxy_adyen_request_direct(
                status_request, "transaction_status"
            )
            status = reply["SaleToPOIResponse"]["TransactionStatusResponse"]
            if status["Response"]["Result"] != "Success":
                return "unconfirmed"
            payment = status["RepeatedMessageResponse"]["RepeatedResponseMessageBody"][
                "PaymentResponse"
            ]
            if (
                payment["SaleData"]["SaleTransactionID"]["TransactionID"]
                != pending["transaction_id"]
            ):
                return "unconfirmed"
            result = payment["Response"]["Result"]
            if result == "Failure":
                return "failed"
            confirmed_amounts = payment["PaymentResult"]["AmountsResp"]
            notified_amounts = data["SaleToPOIResponse"]["PaymentResponse"][
                "PaymentResult"
            ]["AmountsResp"]
            if (
                result == "Success"
                and self._adyen_amounts_match(confirmed_amounts, pending)
                and confirmed_amounts["AuthorizedAmount"]
                == notified_amounts["AuthorizedAmount"]
            ):
                return "confirmed"
        except KeyError, TypeError, ValueError, AttributeError, OSError:
            _logger.warning(
                "Adyen could not confirm the payment of request %s on %s",
                pending["service_id"],
                self.adyen_terminal_identifier,
                exc_info=True,
            )
        return "unconfirmed"

    @api.model
    def _adyen_reported_failed(self, data):
        response = data["SaleToPOIResponse"]["PaymentResponse"]["Response"]
        response["Result"] = "Failure"
        response["AdditionalResponse"] = urlencode(
            {"message": self.env._("Adyen reports this payment as failed.")}
        )
        return data

    def _adyen_settle(self, data, pending, state) -> None:
        transaction_id = data["SaleToPOIResponse"]["PaymentResponse"]["SaleData"][
            "SaleTransactionID"
        ]["TransactionID"]
        session_id = (transaction_id or "").rpartition("--")[2]
        if not session_id.isdecimal():
            return
        session = self.env["pos.session"].sudo().browse(int(session_id)).exists()
        if session:
            session.config_id._notify("ADYEN_LATEST_RESPONSE", session.config_id.id)

    def _integration_connection_service(self):
        if self.use_payment_terminal == "adyen":
            return "pos_adyen", self.env._("Point of Sale: Adyen"), "payment"
        return super()._integration_connection_service()

    _CREDENTIAL_FIELDS = {
        "adyen_api_key": "adyen_api_key",
    }

    def _selection_payment_terminals(self):
        return super()._selection_payment_terminals() + [("adyen", "Adyen")]

    adyen_api_key = fields.Char(
        string="Adyen API key",
        compute="_compute_credential_doors",
        inverse="_inverse_credential_doors",
        classification="secret.credential",
        groups="base.group_erp_manager",
        help="Used when connecting to Adyen: https://docs.adyen.com/user-management/how-to-get-the-api-key/#description",
    )
    adyen_terminal_identifier = fields.Char(
        copy=False,
        help="[Terminal model]-[Serial number], for example: P400Plus-123456789",
    )
    adyen_test_mode = fields.Boolean(
        groups="base.group_erp_manager",
        help="Run transactions in the test environment.",
    )

    adyen_latest_response = fields.Char(
        copy=False,
        groups="base.group_erp_manager",
    )
    adyen_pending_request = fields.Char(
        copy=False,
        classification="base.internal",
        groups="base.group_erp_manager",
    )
    adyen_confirmed_request = fields.Char(
        copy=False,
        classification="base.internal",
        groups="base.group_erp_manager",
    )
    adyen_confirmation_state = fields.Char(
        copy=False,
        classification="base.internal",
        groups="base.group_erp_manager",
    )
    adyen_event_url = fields.Char(
        string="Event URL",
        default=lambda self: f"{self.get_base_url()}/pos_adyen/notification",
        store=False,
        readonly=True,
        help="This URL needs to be pasted on Adyen's portal terminal settings.",
    )

    @api.model
    def _load_pos_data_fields(self, config):
        params = super()._load_pos_data_fields(config)
        params += ["adyen_terminal_identifier"]
        return params

    @api.constrains("adyen_terminal_identifier")
    def _check_adyen_terminal_identifier(self) -> None:
        for payment_method in self:
            if not payment_method.adyen_terminal_identifier:
                continue
            existing_payment_method = self.sudo().search(  # noqa: E8507 -- one probe per method, on its own terminal identifier
                [
                    ("id", "!=", payment_method.id),
                    (
                        "adyen_terminal_identifier",
                        "=",
                        payment_method.adyen_terminal_identifier,
                    ),
                ],
                limit=1,
            )
            if existing_payment_method:
                if existing_payment_method.company_id == payment_method.company_id:
                    raise ValidationError(
                        self.env._(
                            "Terminal %(terminal)s is already used on payment method %(payment_method)s.",
                            terminal=payment_method.adyen_terminal_identifier,
                            payment_method=existing_payment_method.display_name,
                        )
                    )
                raise ValidationError(
                    self.env._(
                        "Terminal %(terminal)s is already used in company %(company)s on payment method %(payment_method)s.",
                        terminal=payment_method.adyen_terminal_identifier,
                        company=existing_payment_method.company_id.name,
                        payment_method=existing_payment_method.display_name,
                    )
                )

    def _get_adyen_endpoints(self) -> dict:
        return {
            "terminal_request": "https://terminal-api-%s.adyen.com/async",
            "transaction_status": "https://terminal-api-%s.adyen.com/sync",
        }

    def _is_write_forbidden(self, fields) -> bool:
        return super()._is_write_forbidden(
            fields
            - {
                "adyen_latest_response",
                "adyen_pending_request",
                "adyen_confirmed_request",
                "adyen_confirmation_state",
            }
        )

    def get_latest_adyen_status(self):
        self.check_singleton()
        if not self.env.su and not self.env.user.has_group(
            "point_of_sale.group_pos_user"
        ):
            raise AccessDenied

        method_sudo = self.sudo()
        if method_sudo.adyen_confirmation_state == "pending":
            method_sudo._adyen_confirm_pending_payment()
        latest_response = method_sudo.adyen_latest_response
        if not latest_response:
            return False
        return {
            **json_loads(latest_response),
            "OdooConfirmation": method_sudo.adyen_confirmation_state or "final",
        }

    def proxy_adyen_request(self, data, operation=False):
        self.check_singleton()
        if not self.env.su and not self.env.user.has_group(
            "point_of_sale.group_pos_user"
        ):
            raise AccessDenied
        if not data:
            raise UserError(self.env._("Invalid Adyen request"))

        if not operation:
            operation = "terminal_request"

        is_capture_data = (
            operation == "capture"
            and hasattr(self, "adyen_merchant_account")
            and self._is_valid_adyen_request_data(
                data,
                {
                    "originalReference": UNPREDICTABLE_ADYEN_DATA,
                    "modificationAmount": {
                        "value": UNPREDICTABLE_ADYEN_DATA,
                        "currency": UNPREDICTABLE_ADYEN_DATA,
                    },
                    "merchantAccount": self.adyen_merchant_account,
                },
            )
        )

        is_adjust_data = (
            operation == "adjust"
            and hasattr(self, "adyen_merchant_account")
            and self._is_valid_adyen_request_data(
                data,
                {
                    "originalReference": UNPREDICTABLE_ADYEN_DATA,
                    "modificationAmount": {
                        "value": UNPREDICTABLE_ADYEN_DATA,
                        "currency": UNPREDICTABLE_ADYEN_DATA,
                    },
                    "merchantAccount": self.adyen_merchant_account,
                    "additionalData": {
                        "industryUsage": "DelayedCharge",
                    },
                },
            )
        )

        is_cancel_data = (
            operation == "terminal_request"
            and self._is_valid_adyen_request_data(
                data,
                {
                    "SaleToPOIRequest": {
                        "MessageHeader": self._get_expected_message_header("Abort"),
                        "AbortRequest": {
                            "AbortReason": "MerchantAbort",
                            "MessageReference": {
                                "MessageCategory": "Payment",
                                "SaleID": UNPREDICTABLE_ADYEN_DATA,
                                "ServiceID": UNPREDICTABLE_ADYEN_DATA,
                            },
                        },
                    },
                },
            )
        )

        is_payment_request_with_acquirer_data = (
            operation == "terminal_request"
            and self._is_valid_adyen_request_data(
                data, self._get_expected_payment_request(True)
            )
        )

        if is_payment_request_with_acquirer_data:
            parsed_sale_to_acquirer_data = parse_qs(
                data["SaleToPOIRequest"]["PaymentRequest"]["SaleData"][
                    "SaleToAcquirerData"
                ]
            )
            valid_acquirer_data = self._prepare_acquirer_data()
            is_payment_request_with_acquirer_data = len(
                parsed_sale_to_acquirer_data.keys()
            ) <= len(valid_acquirer_data.keys())
            if is_payment_request_with_acquirer_data:
                for key, values in parsed_sale_to_acquirer_data.items():
                    if len(values) != 1:
                        is_payment_request_with_acquirer_data = False
                        break
                    value = values[0]
                    valid_value = valid_acquirer_data.get(key)
                    if valid_value == UNPREDICTABLE_ADYEN_DATA:
                        continue
                    if value != valid_value:
                        is_payment_request_with_acquirer_data = False
                        break

        is_payment_request_without_acquirer_data = (
            operation == "terminal_request"
            and self._is_valid_adyen_request_data(
                data, self._get_expected_payment_request(False)
            )
        )

        if (
            not is_payment_request_without_acquirer_data
            and not is_payment_request_with_acquirer_data
            and not is_adjust_data
            and not is_cancel_data
            and not is_capture_data
        ):
            raise UserError(self.env._("Invalid Adyen request"))

        if (
            is_payment_request_with_acquirer_data
            or is_payment_request_without_acquirer_data
        ):
            self._adyen_sign_payment_request(data)

        return self._proxy_adyen_request_direct(data, operation)

    @api.model
    def _is_valid_adyen_request_data(self, provided_data, expected_data) -> bool:
        if not isinstance(provided_data, dict) or set(provided_data.keys()) != set(
            expected_data.keys()
        ):
            return False

        for provided_key, provided_value in provided_data.items():
            expected_value = expected_data[provided_key]
            if expected_value == UNPREDICTABLE_ADYEN_DATA:
                continue
            if isinstance(expected_value, dict):
                if not self._is_valid_adyen_request_data(
                    provided_value, expected_value
                ):
                    return False
            elif provided_value != expected_value:
                return False
        return True

    def _get_expected_message_header(self, expected_message_category) -> dict:
        return {
            "ProtocolVersion": "3.0",
            "MessageClass": "Service",
            "MessageType": "Request",
            "MessageCategory": expected_message_category,
            "SaleID": UNPREDICTABLE_ADYEN_DATA,
            "ServiceID": UNPREDICTABLE_ADYEN_DATA,
            "POIID": self.adyen_terminal_identifier,
        }

    def _get_expected_payment_request(self, with_acquirer_data):
        res = {
            "SaleToPOIRequest": {
                "MessageHeader": self._get_expected_message_header("Payment"),
                "PaymentRequest": {
                    "SaleData": {
                        "SaleTransactionID": {
                            "TransactionID": UNPREDICTABLE_ADYEN_DATA,
                            "TimeStamp": UNPREDICTABLE_ADYEN_DATA,
                        },
                    },
                    "PaymentTransaction": {
                        "AmountsReq": {
                            "Currency": UNPREDICTABLE_ADYEN_DATA,
                            "RequestedAmount": UNPREDICTABLE_ADYEN_DATA,
                        },
                    },
                },
            },
        }

        if with_acquirer_data:
            res["SaleToPOIRequest"]["PaymentRequest"]["SaleData"][
                "SaleToAcquirerData"
            ] = UNPREDICTABLE_ADYEN_DATA
        return res

    @api.model
    def _prepare_acquirer_data(self):
        return {"tenderOption": "AskGratuity", "authorisationType": "PreAuth"}

    def _adyen_sign_payment_request(self, data, self_order_id=False) -> None:
        msg_header = data["SaleToPOIRequest"]["MessageHeader"]
        payment_request = data["SaleToPOIRequest"]["PaymentRequest"]
        sale_data = payment_request["SaleData"]
        amounts = payment_request["PaymentTransaction"]["AmountsReq"]
        transaction_id = sale_data["SaleTransactionID"]["TransactionID"]
        amount = amounts["RequestedAmount"]
        if not isinstance(amount, int | float) or isinstance(amount, bool):
            raise UserError(self.env._("Invalid Adyen request"))
        metadata = "metadata.pos_hmac=" + self._get_hmac(
            msg_header["SaleID"],
            msg_header["ServiceID"],
            msg_header["POIID"],
            transaction_id,
        )
        acquirer_data = sale_data.get("SaleToAcquirerData")
        sale_data["SaleToAcquirerData"] = (
            f"{acquirer_data}&{metadata}" if acquirer_data else metadata
        )
        self.sudo().write(
            {
                "adyen_latest_response": "",
                "adyen_confirmed_request": False,
                "adyen_confirmation_state": False,
                "adyen_pending_request": json_dumps(
                    {
                        "sale_id": msg_header["SaleID"],
                        "service_id": msg_header["ServiceID"],
                        "transaction_id": transaction_id,
                        "currency": amounts["Currency"],
                        "amount": amount,
                        "self_order_id": self_order_id,
                    }
                ),
            }
        )

    @api.model
    def _get_hmac(self, sale_id, service_id, poi_id, sale_transaction_id):
        return hmac(
            env=self.env(su=True),
            scope=PAYMENT_SCOPE,
            message=(sale_id, service_id, poi_id, sale_transaction_id),
        )

    def _proxy_adyen_request_direct(self, data, operation):
        self.check_singleton()
        TIMEOUT = 10

        _logger.info(
            "Request to Adyen by user #%d:\n%s",
            self.env.uid,
            pprint.pformat(redact_pos_hmac(data)),
        )

        environment = "test" if self.sudo().adyen_test_mode else "live"
        endpoint = self._get_adyen_endpoints()[operation] % environment
        headers = {
            "x-api-key": self.sudo().adyen_api_key,
        }
        req = self._get_integration_connection()._egress_request(
            "POST",
            endpoint,
            purpose="pos_adyen",
            json=data,
            headers=headers,
            timeout=TIMEOUT,
        )

        if req.status_code == 401:
            return {"error": {"status_code": req.status_code, "message": req.text}}

        if req.text == "ok":
            return True

        return req.json()
