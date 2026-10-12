import hashlib
import hmac
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlencode as url_encode

from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tests import tagged
from odoo.tools import mute_logger
from odoo.tools.urls import urljoin as url_join

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_stripe import const
from odoo.addons.payment_stripe import utils as stripe_utils
from odoo.addons.payment_stripe.controllers.main import StripeController
from odoo.addons.payment_stripe.models.payment_transaction import (
    PaymentTransaction,
)
from odoo.addons.payment_stripe.tests.common import StripeCommon


@tagged("post_install", "-at_install")
class StripeTest(StripeCommon, PaymentHttpCommon):
    def test_processing_values(self):
        dummy_client_secret = "pi_123456789_secret_dummy_123456789"
        tx = self._create_transaction(flow="direct")

        def mock_stripe_stripe_create_intent(self):
            return {"client_secret": dummy_client_secret}

        with (
            patch.object(
                type(self.env["payment.transaction"]),
                "_stripe_create_intent",
                mock_stripe_stripe_create_intent,
            ),
            mute_logger("odoo.addons.payment.models.payment_transaction"),
        ):
            processing_values = tx._prepare_processing_values()

        self.assertEqual(processing_values["client_secret"], dummy_client_secret)

        base_url = self.provider.get_base_url()
        return_url = url_join(
            base_url,
            f"{StripeController._return_url}?{url_encode({'reference': tx.reference})}",
        )
        self.assertEqual(processing_values["return_url"], return_url)

    @mute_logger("odoo.addons.payment_stripe.models.payment_transaction")
    def test_tx_state_after_send_capture_request(self):
        self.provider.capture_manually = True
        tx = self._create_transaction("direct", state="authorized")

        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
            return_value={
                "id": "pi_3KTk9zAlCFm536g81Wy7RCPH",
                "status": "succeeded",
                **self.notification_amount_and_currency,
            },
        ):
            tx._capture()
        self.assertEqual(
            tx.state,
            "done",
            msg="The state should be 'done' after a successful capture.",
        )

    @mute_logger("odoo.addons.payment_stripe.models.payment_transaction")
    def test_tx_state_after_send_void_request(self):
        self.provider.capture_manually = True
        tx = self._create_transaction("redirect", state="authorized")

        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
            return_value={
                "id": "pi_3KTk9zAlCFm536g81Wy7RCPH",
                "status": "canceled",
                **self.notification_amount_and_currency,
            },
        ):
            child_tx = tx._void()
        self.assertEqual(
            child_tx.state,
            "cancel",
            msg="The state should be 'cancel' after voiding the transaction.",
        )

    @mute_logger("odoo.addons.payment_stripe.controllers.main")
    def test_webhook_notification_confirms_transaction(self):
        tx = self._create_transaction("redirect")
        url = self._build_url(StripeController._webhook_url)
        with patch(
            "odoo.addons.payment_stripe.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
        ):
            self._make_json_request(url, data=self.payment_data)
        self.assertEqual(tx.state, "done")

    @mute_logger("odoo.addons.payment_stripe.controllers.main")
    def test_an_admitted_webhook_is_recorded_on_the_providers_receiver(self):
        self._create_transaction("redirect")
        url = self._build_url(StripeController._webhook_url)
        with patch(
            "odoo.addons.payment_stripe.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
        ):
            self._make_json_request(url, data=self.payment_data)
        receiver = self.env["integration.receiver"].search(
            [("res_model", "=", "payment.provider"), ("res_id", "=", self.stripe.id)]
        )
        self.assertEqual(receiver.auth_type, "caller_check")
        exchange = self.env["integration.exchange"].search(
            [("channel_id", "=", f"integration.receiver,{receiver.id}")]
        )
        self.assertEqual(len(exchange), 1)
        self.assertEqual(exchange.direction, "inbound")

    @mute_logger("odoo.addons.payment_stripe.controllers.main")
    def test_a_redelivered_event_is_acknowledged_and_not_processed_again(self):
        tx = self._create_transaction("redirect")
        url = self._build_url(StripeController._webhook_url)
        event = {**self.payment_data, "id": "evt_redelivered_1"}
        with patch(
            "odoo.addons.payment_stripe.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
        ):
            first = self._make_json_request(url, data=event)
            tx.state = "draft"
            second = self._make_json_request(url, data=event)
        self.assertEqual((first.status_code, second.status_code), (200, 200))
        self.assertEqual(tx.state, "draft", "the redelivery did not run the handler")
        receiver = self.env["integration.receiver"].search(
            [("res_model", "=", "payment.provider"), ("res_id", "=", self.stripe.id)]
        )
        rows = self.env["integration.exchange"].search(
            [("channel_id", "=", f"integration.receiver,{receiver.id}")], order="id"
        )
        self.assertEqual(rows.mapped("event_id_external"), ["evt_redelivered_1", False])
        self.assertEqual(rows.mapped("state"), ["success", "refused"])
        self.assertEqual(rows[-1].refusal_reason, "duplicate_event")

    @mute_logger(
        "odoo.addons.payment_stripe.controllers.main",
        "odoo.addons.integration.models.integration_receiver",
        "odoo.addons.integration.models.mixin_inbound_gate",
        "odoo.http",
    )
    def test_a_webhook_with_a_bad_signature_is_refused_and_logged(self):
        tx = self._create_transaction("redirect")
        url = self._build_url(StripeController._webhook_url)
        Receiver = type(self.env["integration.receiver"])
        store_refusal = Receiver._store_inbound_refusal
        verdicts = []

        def spy(receiver, code, *args, **kwargs):
            verdicts.append(
                (receiver.res_id, code, receiver.env.cr is not request.env.cr)
            )
            return store_refusal(receiver, code, *args, **kwargs)

        with patch.object(Receiver, "_store_inbound_refusal", spy):
            response = self._make_json_request(url, data=self.payment_data)

        self.assertEqual(response.status_code, 401)
        self.assertNotEqual(tx.state, "done")
        self.assertEqual(
            verdicts,
            [(self.stripe.id, "authentication_failed", True)],
            "the refusal is stored on its own cursor, which the request's "
            "rollback does not discard",
        )

    def test_validate_amount_succeeds_for_special_currencies(self):
        for currency_code in const.CURRENCY_DECIMALS:
            currency = self._enable_currency(currency_code)
            tx = self._create_transaction(
                "dummy",
                operation="online_direct",
                amount=15,
                currency_id=currency.id,
                reference=f"test_{currency_code}",
            )
            data = self.payment_data["data"]
            with patch(
                "odoo.addons.payment_stripe.models.payment_transaction.PaymentTransaction"
                "._stripe_create_customer",
                return_value={"id": "cus_1234567890ABCDE"},
            ):
                data["payment_intent"] = tx._stripe_prepare_payment_intent_payload()
            tx._check_amount(data)
            self.assertNotEqual(tx.state, "error")

    def test_extract_token_values_maps_fields_correctly(self):
        tx = self._create_transaction("direct")
        payment_data = {
            "payment_intent": {
                "charges": {"data": [{}]},
                "customer": "test_customer",
            },
            "payment_method": {
                "card": {"brand": "visa", "last4": "1111"},
                "id": "pm_test",
                "object": "payment_method",
                "type": "card",
            },
        }
        token_values = tx._extract_token_values(payment_data)
        self.assertDictEqual(
            token_values,
            {
                "payment_details": "1111",
                "provider_ref": "test_customer",
                "stripe_mandate": None,
                "stripe_payment_method": "pm_test",
            },
        )

    @mute_logger("odoo.addons.payment_stripe.controllers.main")
    def test_webhook_notification_tokenizes_payment_method(self):
        self.amount = 0.0
        self._create_transaction("dummy", operation="validation", tokenize=True)
        url = self._build_url(StripeController._webhook_url)
        data = self.payment_data["data"]
        payment_method_response = data["object"] = self._mock_setup_intent_request()
        with (
            patch(
                "odoo.addons.payment_stripe.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
            ),
            patch(
                "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
                return_value=payment_method_response,
            ),
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._tokenize"
            ) as tokenize_check_mock,
        ):
            self._make_json_request(
                url, data=dict(self.payment_data, type="setup_intent.succeeded")
            )
        self.assertEqual(tokenize_check_mock.call_count, 1)

    @mute_logger("odoo.addons.payment_stripe.controllers.main")
    def test_webhook_notification_triggers_signature_check(self):
        self._create_transaction("redirect")
        url = self._build_url(StripeController._webhook_url)
        with (
            patch(
                "odoo.addons.payment_stripe.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
            ) as signature_check_mock,
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ),
        ):
            self._make_json_request(url, data=self.payment_data)
            self.assertEqual(signature_check_mock.call_count, 1)

    @mute_logger("odoo.addons.payment_stripe.controllers.main")
    @mute_logger("odoo.addons.payment_stripe.models.payment_transaction")
    def test_webhook_notification_skips_signature_verification_for_missing_transactions(
        self,
    ):
        url = self._build_url(StripeController._webhook_url)
        payload = dict(self.payment_data)
        payload["data"]["object"]["description"] = None

        with patch(
            "odoo.addons.payment_stripe.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
        ) as signature_check_mock:
            self._make_json_request(url, data=payload)
            self.assertEqual(signature_check_mock.call_count, 0)

    @mute_logger("odoo.addons.payment_stripe.controllers.main")
    def test_return_from_tokenization_request(self):
        tx = self._create_transaction(
            "direct", amount=0, operation="validation", tokenize=True
        )
        url = self._build_url(StripeController._return_url)
        PaymentProvider = self.env.registry["payment.provider"]
        with (
            patch.object(
                PaymentTransaction, "_is_inbound_request_authentic", return_value=True
            ),
            patch.object(
                PaymentProvider, "_send_api_request", self._mock_setup_intent_request
            ),
        ):
            res = self._make_http_get_request(url, params={"reference": tx.reference})
            self.assertTrue(res.ok, msg=res.content.decode())

    @mute_logger("odoo.addons.payment_stripe.controllers.main")
    def test_return_url_client_secret_stays_out_of_the_access_log(self):
        tx = self._create_transaction(
            "direct", amount=0, operation="validation", tokenize=True
        )
        url = self._build_url(StripeController._return_url)
        secret = "seti_123_secret_ReturnUrlSecret987"
        PaymentProvider = self.env.registry["payment.provider"]
        with (
            patch.object(
                PaymentTransaction, "_is_inbound_request_authentic", return_value=True
            ),
            patch.object(
                PaymentProvider, "_send_api_request", self._mock_setup_intent_request
            ),
            self.assertLogs("odoo.service.http.access", "INFO") as capture,
        ):
            res = self._make_http_get_request(
                url,
                params={
                    "reference": tx.reference,
                    "setup_intent": "seti_123",
                    "setup_intent_client_secret": secret,
                },
            )
            self.assertTrue(res.ok, msg=res.content.decode())
        log = "\n".join(capture.output)
        self.assertIn(StripeController._return_url, log)
        self.assertNotIn(secret, log)
        self.assertIn("setup_intent_client_secret=***REDACTED***", log)

    def test_onboarding_action_redirect_to_url(self):
        if country := self.env["res.country"].search(
            [("code", "in", list(const.SUPPORTED_COUNTRIES))], limit=1
        ):
            self.env.company.country_id = country
        else:
            raise unittest.SkipTest(
                "Unable to find a country supported by both odoo and stripe"
            )

        with (
            patch.object(
                type(self.env["payment.provider"]),
                "_stripe_get_or_create_connected_account",
                return_value={"id": "dummy"},
            ),
            patch.object(
                type(self.env["payment.provider"]),
                "_stripe_create_account_link",
                return_value="https://dummy.url",
            ),
        ):
            onboarding_url = self.stripe.action_start_onboarding()
        self.assertEqual(onboarding_url["url"], "https://dummy.url")

    def test_country_mapping_stripe_connect(self):
        mapped_country_company = self.env["res.company"].create(
            {
                "name": "Mapped Company",
            }
        )
        with (
            patch.object(
                self.env.registry["payment.provider"],
                "_send_api_request",
                return_value={"url": "https://dummy.url"},
            ) as mock,
            patch.object(
                self.env.registry["payment.provider"],
                "_stripe_get_or_create_connected_account",
                return_value={"id": "dummy"},
            ),
        ):
            for country_code in const.COUNTRY_MAPPING:
                country = self.env["res.country"].search(
                    [("code", "=", country_code)], limit=1
                )
                mapped_country_company.country_id = country
                self.stripe.with_company(
                    mapped_country_company
                ).action_start_onboarding("dummy")
            self.assertEqual(mock.call_count, len(const.COUNTRY_MAPPING))

    def test_the_secrets_live_in_the_providers_credential(self):
        self.stripe.write(
            {"stripe_secret_key": "sk_vault", "stripe_webhook_secret": "wh"}
        )
        self.stripe.stripe_webhook_secret = "wh_rotated"
        self.stripe.invalidate_recordset()

        credential = self.stripe.provider_credential_id
        self.assertTrue(credential)
        self.assertFalse(self.stripe._fields["stripe_secret_key"].store)
        self.assertEqual(
            (self.stripe.stripe_secret_key, self.stripe.stripe_webhook_secret),
            ("sk_vault", "wh_rotated"),
        )
        self.assertEqual(
            credential.sudo()._use_secret_payload("payment:provider"),
            {"stripe_secret_key": "sk_vault", "stripe_webhook_secret": "wh_rotated"},
        )

    def test_clearing_every_secret_unlinks_the_credential(self):
        self.stripe.write(
            {"stripe_secret_key": "sk_vault", "stripe_webhook_secret": "wh"}
        )
        credential = self.stripe.provider_credential_id

        self.stripe.write(
            {
                "state": "disabled",
                "stripe_secret_key": False,
                "stripe_webhook_secret": False,
            }
        )

        self.assertFalse(self.stripe.provider_credential_id)
        self.assertFalse(credential.exists())

    def test_a_required_secret_is_still_required_once_it_is_a_door(self):
        self.stripe.write({"state": "test", "stripe_secret_key": "sk_vault"})
        with self.assertRaises(ValidationError):
            self.stripe.stripe_secret_key = False

    def test_only_create_webhook_if_not_already_done(self):
        self.stripe.stripe_webhook_secret = False
        with patch.object(
            self.env.registry["payment.provider"], "_send_api_request"
        ) as mock:
            self.stripe.action_stripe_create_webhook()
            self.assertEqual(mock.call_count, 1)

    def test_do_not_create_webhook_if_already_done(self):
        self.stripe.stripe_webhook_secret = "dummy"
        with patch.object(
            self.env.registry["payment.provider"], "_send_api_request"
        ) as mock:
            self.stripe.action_stripe_create_webhook()
            self.assertEqual(mock.call_count, 0)

    def test_create_account_link_pass_required_parameters(self):
        with patch.object(
            self.env.registry["payment.provider"],
            "_send_api_request",
            return_value={"url": "https://dummy.url"},
        ) as mock:
            self.stripe._stripe_create_account_link("dummy", "dummy")
            mock.assert_called_once()
            call_args = mock.call_args.kwargs["json"]["params"]["payload"].keys()
            for payload_param in ("account", "return_url", "refresh_url", "type"):
                self.assertIn(payload_param, call_args)

    @mute_logger("odoo.addons.payment_stripe.models.payment_transaction")
    def test_a_webhook_with_a_non_ascii_signature_is_refused_not_raised_on(self):
        tx = self._create_transaction("redirect")
        headers = {"Stripe-Signature": f"t={int(time.time())},v1={'é' * 64}"}
        self.assertFalse(tx._is_inbound_request_authentic(headers, b"{}"))

    @mute_logger("odoo.addons.payment_stripe.models.payment_transaction")
    def test_a_webhook_with_a_malformed_signature_timestamp_is_refused_without_a_traceback(
        self,
    ):
        self._create_transaction("redirect")
        url = self._build_url(StripeController._webhook_url)
        for timestamp in ("soon", "1.7e9", "0170000000", "1" * 5000):
            with self.subTest(timestamp=timestamp[:12]):
                with self._assertNoTracebackLogged():
                    response = self.url_open(
                        url,
                        json=self.payment_data,
                        headers={"Stripe-Signature": f"t={timestamp},v1={'0' * 64}"},
                    )
                self.assertEqual(response.status_code, 401)

    def test_a_webhook_whose_body_is_no_stripe_event_is_refused_without_a_traceback(
        self,
    ):
        url = self._build_url(StripeController._webhook_url)
        event_type = const.HANDLED_WEBHOOK_EVENTS[0]
        for body in (
            "not json",
            [],
            {"type": event_type},
            {"type": event_type, "data": []},
            {"type": event_type, "data": {"object": "pi_1"}},
        ):
            with self.subTest(body=body):
                self.assertEqual(self._post_malformed_json(url, body).status_code, 400)

    @mute_logger("odoo.addons.payment_stripe.models.payment_transaction")
    def test_a_signed_timestamp_verifies_as_the_digits_stripe_sends_and_not_zero_padded(
        self,
    ):
        tx = self._create_transaction("redirect")
        secret = stripe_utils.get_webhook_secret(self.stripe).encode()
        body = b"{}"
        now = int(time.time())
        for timestamp, verified in ((str(now), True), (f"0{now}", False)):
            signature = hmac.new(
                secret, f"{timestamp}.{body.decode()}".encode(), hashlib.sha256
            ).hexdigest()
            with self.subTest(timestamp=timestamp):
                self.assertEqual(
                    tx._is_inbound_request_authentic(
                        {"Stripe-Signature": f"t={timestamp},v1={signature}"}, body
                    ),
                    verified,
                )

    @mute_logger("odoo.addons.payment_stripe.models.payment_transaction")
    def test_an_event_whose_object_has_no_id_reaches_the_signature_check_without_a_traceback(
        self,
    ):
        tx = self._create_transaction("redirect")
        url = self._build_url(StripeController._webhook_url)
        body = {
            "type": "payment_intent.succeeded",
            "data": {"object": {"description": tx.reference}},
        }
        self.assertEqual(self._post_malformed_json(url, body).status_code, 401)

    @mute_logger("odoo.addons.payment_stripe.models.payment_transaction")
    def test_a_refund_event_that_names_no_refund_matches_no_transaction(self):
        self._create_transaction("redirect")
        self.assertFalse(
            self.env["payment.transaction"]._search_by_reference(
                "stripe", {"event_type": "charge.refund.updated", "object_id": None}
            )
        )

    @mute_logger("odoo.addons.payment_stripe.models.payment_transaction")
    def test_a_webhook_whose_references_are_no_strings_is_acknowledged_without_a_traceback(
        self,
    ):
        first = self._create_transaction("redirect", reference="ref-1")
        second = self._create_transaction("redirect", reference="ref-2")
        first.provider_reference, second.provider_reference = "re_1", "re_2"
        url = self._build_url(StripeController._webhook_url)
        for stripe_object in (
            {"description": [first.reference, second.reference], "id": "pi_1"},
            {"description": {first.reference: 1}, "id": "pi_1"},
            {"id": [first.provider_reference, second.provider_reference]},
        ):
            event_type = (
                "payment_intent.succeeded"
                if "description" in stripe_object
                else "charge.refund.updated"
            )
            body = {"type": event_type, "data": {"object": stripe_object}}
            with self.subTest(body=body):
                self.assertEqual(self._post_malformed_json(url, body).status_code, 200)
