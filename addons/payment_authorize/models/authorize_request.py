import pprint
from uuid import uuid4

from odoo.libs.json import dumps as json_dumps
from odoo.libs.json import loads as json_loads

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class AuthorizeAPI:
    """Authorize.net Gateway API integration.

    This class allows contacting the Authorize.net API with simple operation
    requests. It implements a *very limited* subset of the complete API
    (http://developer.authorize.net/api/reference); namely:
        - Customer Profile/Payment Profile creation
        - Transaction authorization/capture/voiding
    """

    AUTH_ERROR_STATUS = "3"

    def __init__(self, provider) -> None:
        if provider.state == "enabled":
            self.url = "https://api.authorize.net/xml/v1/request.api"
        else:
            self.url = "https://apitest.authorize.net/xml/v1/request.api"

        self.env = provider.env
        self.connection = provider._get_integration_connection()
        self.state = provider.state
        self.name = provider.authorize_login
        self.transaction_key = provider.authorize_transaction_key

    def _prepare_request(self, operation, data=None):
        request = {
            operation: {
                "merchantAuthentication": {
                    "name": self.name,
                    "transactionKey": self.transaction_key,
                },
                **(data or {}),
            }
        }
        logged_request = {operation: data or {}}

        _logger.info(
            "sending request to %s:\n%s", self.url, pprint.pformat(logged_request)
        )
        response = self.connection._egress_request(
            "POST",
            self.url,
            purpose="payment_authorize",
            data=json_dumps(request),
            timeout=60,
        )
        response.raise_for_status()
        response = json_loads(response.content)
        _logger.info("response received:\n%s", pprint.pformat(response))

        messages = response.get("messages")
        if messages and messages.get("resultCode") == "Error":
            err_msg = messages.get("message")[0]["text"]

            tx_errors = response.get("transactionResponse", {}).get("errors")
            if tx_errors:
                if err_msg:
                    err_msg += "\n"
                err_msg += "\n".join([e.get("errorText", "") for e in tx_errors])

            return {
                "err_code": messages.get("message")[0].get("code"),
                "err_msg": err_msg,
            }

        return response

    def _format_response(self, response, operation):
        if response and response.get("err_code"):
            return {
                "x_response_code": self.AUTH_ERROR_STATUS,
                "x_response_reason_text": response.get("err_msg"),
            }
        else:
            tx_response = response.get("transactionResponse", {})
            return {
                "x_response_code": tx_response.get("responseCode"),
                "x_trans_id": tx_response.get("transId"),
                "x_type": operation,
                "payment_method_code": tx_response.get("accountType"),
            }

    def create_customer_profile(self, partner, transaction_id):
        response = self._prepare_request(
            "createCustomerProfileFromTransactionRequest",
            {
                "transId": transaction_id,
                "customer": {
                    "merchantCustomerId": (
                        "ODOO-%s-%s" % (partner.id, uuid4().hex[:8])
                    )[:20],
                    "email": partner.email or "",
                },
            },
        )

        if not response.get("customerProfileId"):
            _logger.warning(
                "unable to create customer payment profile, data missing from transaction with "
                "id %(tx_id)s, partner id: %(partner_id)s",
                {
                    "tx_id": transaction_id,
                    "partner_id": partner,
                },
            )
            return False

        res = {
            "profile_id": response.get("customerProfileId"),
            "payment_profile_id": response.get("customerPaymentProfileIdList")[0],
        }

        response = self._prepare_request(
            "getCustomerPaymentProfileRequest",
            {
                "customerProfileId": res["profile_id"],
                "customerPaymentProfileId": res["payment_profile_id"],
            },
        )

        payment = response.get("paymentProfile", {}).get("payment", {})
        if "creditCard" in payment:
            res["payment_details"] = payment.get("creditCard", {}).get("cardNumber")[
                -4:
            ]
        else:
            res["payment_details"] = payment.get("bankAccount", {}).get(
                "accountNumber"
            )[-4:]
        return res

    def remove_customer_profile(self, profile_id):
        response = self._prepare_request(
            "deleteCustomerProfileRequest", {"customerProfileId": profile_id}
        )
        return self._format_response(response, "deleteCustomerProfile")

    def _prepare_authorization_transaction_request(
        self, transaction_type, tx_data, tx
    ) -> dict:
        bill_to = {}
        if "profile" not in tx_data:
            if tx.partner_id.is_company:
                split_name = "", tx.partner_name
            else:
                split_name = payment_utils.split_partner_name(tx.partner_name)
            bill_to = {
                "billTo": {
                    "firstName": split_name[0][:50],
                    "lastName": split_name[1][:50],
                    "company": tx.partner_name[:50] if tx.partner_id.is_company else "",
                    "address": tx.partner_address,
                    "city": tx.partner_city,
                    "state": tx.partner_state_id.name or "",
                    "zip": tx.partner_zip,
                    "country": tx.partner_country_id.name or "",
                }
            }

        return {
            "transactionRequest": {
                "transactionType": transaction_type,
                "amount": str(tx.amount),
                **tx_data,
                "order": {
                    "invoiceNumber": tx.reference[:20],
                    "description": tx.reference[:255],
                },
                "customer": {
                    "email": tx.partner_email or "",
                },
                **bill_to,
                "customerIP": payment_utils.get_customer_ip_address(),
            }
        }

    def authorize(self, tx, token=None, opaque_data=None):
        tx_data = self._prepare_tx_data(token=token, opaque_data=opaque_data)
        response = self._prepare_request(
            "createTransactionRequest",
            self._prepare_authorization_transaction_request(
                "authOnlyTransaction", tx_data, tx
            ),
        )
        return self._format_response(response, "auth_only")

    def auth_and_capture(self, tx, token=None, opaque_data=None):
        tx_data = self._prepare_tx_data(token=token, opaque_data=opaque_data)
        response = self._prepare_request(
            "createTransactionRequest",
            self._prepare_authorization_transaction_request(
                "authCaptureTransaction", tx_data, tx
            ),
        )

        result = self._format_response(response, "auth_capture")
        errors = response.get("transactionResponse", {}).get("errors")
        if errors:
            result["x_response_reason_text"] = "\n".join(
                [e.get("errorText") for e in errors]
            )
        return result

    def _prepare_tx_data(self, token=None, opaque_data=False) -> dict:
        assert (token or opaque_data) and not (token and opaque_data), (
            "Exactly one of token or opaque_data must be specified"
        )
        if token:
            token.check_singleton()
            return {
                "profile": {
                    "customerProfileId": token.authorize_profile,
                    "paymentProfile": {
                        "paymentProfileId": token.provider_ref,
                    },
                },
            }
        else:
            return {
                "payment": {
                    "opaqueData": opaque_data,
                }
            }

    def get_transaction_details(self, transaction_id):
        return self._prepare_request(
            "getTransactionDetailsRequest", {"transId": transaction_id}
        )

    def capture(self, transaction_id, amount):
        response = self._prepare_request(
            "createTransactionRequest",
            {
                "transactionRequest": {
                    "transactionType": "priorAuthCaptureTransaction",
                    "amount": str(amount),
                    "refTransId": transaction_id,
                }
            },
        )
        return self._format_response(response, "prior_auth_capture")

    def void(self, transaction_id):
        response = self._prepare_request(
            "createTransactionRequest",
            {
                "transactionRequest": {
                    "transactionType": "voidTransaction",
                    "refTransId": transaction_id,
                }
            },
        )
        return self._format_response(response, "void")

    def refund(self, transaction_id, amount, tx_details):
        card = (
            tx_details.get("transaction", {})
            .get("payment", {})
            .get("creditCard", {})
            .get("cardNumber")
        )
        response = self._prepare_request(
            "createTransactionRequest",
            {
                "transactionRequest": {
                    "transactionType": "refundTransaction",
                    "amount": str(amount),
                    "payment": {
                        "creditCard": {
                            "cardNumber": card,
                            "expirationDate": "XXXX",
                        }
                    },
                    "refTransId": transaction_id,
                }
            },
        )
        return self._format_response(response, "refund")

    def merchant_details(self):
        return self._prepare_request("getMerchantDetailsRequest")

    def test_authenticate(self):
        return self._prepare_request("authenticateTestRequest")
