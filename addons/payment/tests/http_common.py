import logging
from contextlib import contextmanager

from lxml import etree, objectify

from odoo.libs.json import dumps as json_dumps
from odoo.libs.web import urls
from odoo.tests import HttpCase, JsonRpcException

from odoo.addons.payment.tests.common import PaymentCommon


class PaymentHttpCommon(PaymentCommon, HttpCase):
    def _build_url(self, route):
        return urls.urljoin(self.base_url(), route)

    def _make_http_get_request(self, url, params=None):
        formatted_params = self._format_http_request_payload(payload=params)
        return self.url_open(url, params=formatted_params)

    def _make_http_post_request(self, url, data=None):
        formatted_data = self._format_http_request_payload(payload=data)
        return self.url_open(url, data=formatted_data, method="POST")

    def _format_http_request_payload(self, payload=None):
        formatted_payload = {}
        if payload is not None:
            for k, v in payload.items():
                formatted_payload[k] = str(v) if isinstance(v, float) else v
        return formatted_payload

    def _make_json_request(self, url, data=None):
        return self.url_open(url, json=data)

    @contextmanager
    def _assertNoTracebackLogged(self):
        with self.assertLogs("odoo", "DEBUG") as capture:
            yield
            logging.getLogger("odoo").debug("end of the checked request")
        self.assertFalse(
            [record.getMessage() for record in capture.records if record.exc_info]
        )

    def _post_malformed_json(self, url, body):
        with self._assertNoTracebackLogged():
            return self.url_open(
                url,
                data=body if isinstance(body, str) else json_dumps(body),
                headers={"Content-Type": "application/json"},
            )

    @contextmanager
    def _assertNotFound(self):
        with self.assertRaises(JsonRpcException) as cm:
            yield
        self.assertEqual(cm.exception.code, 404)

    def _get_payment_context(self, response):
        html_tree = objectify.fromstring(
            response.text,
            parser=etree.HTMLParser(),
        )
        payment_form = html_tree.xpath('//form[@id="o_payment_form"]')[0]
        values = {}
        for key, val in payment_form.items():
            if key.startswith("data-"):
                formatted_key = key[5:].replace("-", "_")
                if formatted_key.endswith("_id"):
                    formatted_val = int(val)
                elif formatted_key == "amount":
                    formatted_val = float(val)
                else:
                    formatted_val = val
                values[formatted_key] = formatted_val

        payment_options_inputs = html_tree.xpath("//input[@name='o_payment_radio']")
        token_ids = []
        payment_method_ids = []
        for p_o_input in payment_options_inputs:
            data = {}
            for key, val in p_o_input.items():
                if key.startswith("data-"):
                    data[key[5:]] = val
            if data["payment-option-type"] == "token":
                token_ids.append(int(data["payment-option-id"]))
            else:
                payment_method_ids.append(int(data["payment-option-id"]))

        values.update(
            {
                "token_ids": token_ids,
                "payment_method_ids": payment_method_ids,
            }
        )

        return values

    def _prepare_pay_values(
        self, amount=0.0, currency=None, reference="", partner=None
    ):
        amount = amount or self.amount
        currency = currency or self.currency
        reference = reference or self.reference
        partner = partner or self.partner
        return {
            "amount": amount,
            "currency_id": currency.id,
            "reference": reference,
            "partner_id": partner.id,
            "access_token": self._generate_test_access_token(
                partner.id, amount, currency.id
            ),
        }

    def _portal_pay(self, **route_kwargs):
        uri = "/payment/pay"
        url = self._build_url(uri)
        return self._make_http_get_request(url, route_kwargs)

    def _get_portal_pay_context(self, **route_kwargs):
        response = self._portal_pay(**route_kwargs)

        self.assertEqual(response.status_code, 200)

        return self._get_payment_context(response)

    def _portal_payment_method(self):
        uri = "/my/payment_method"
        url = self._build_url(uri)
        return self._make_http_get_request(url, {})

    def _get_portal_payment_method_context(self):
        response = self._portal_payment_method()

        self.assertEqual(response.status_code, 200)

        return self._get_payment_context(response)

    def _prepare_transaction_values(self, payment_method_id, token_id, flow):
        return {
            "provider_id": self.provider.id,
            "payment_method_id": payment_method_id,
            "token_id": token_id,
            "amount": self.amount,
            "currency_id": self.currency.id,
            "partner_id": self.partner.id,
            "access_token": self._generate_test_access_token(
                self.partner.id, self.amount, self.currency.id
            ),
            "tokenization_requested": True,
            "landing_route": "Test",
            "reference_prefix": "test",
            "is_validation": False,
            "flow": flow,
        }

    def _portal_transaction(self, tx_route="/payment/transaction", **route_kwargs):
        url = self._build_url(tx_route)
        return self.call_jsonrpc(url, route_kwargs)

    def _get_processing_values(self, **route_kwargs):
        return self._portal_transaction(**route_kwargs)
