from unittest.mock import patch

from odoo.libs.json import dumps as json_dumps
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_razorpay.controllers.main import RazorpayController
from odoo.addons.payment_razorpay.tests.common import RazorpayCommon


@tagged("post_install", "-at_install")
class TestProcessingFlows(RazorpayCommon, PaymentHttpCommon):
    @mute_logger("odoo.addons.payment_razorpay.models.payment_transaction")
    def test_webhook_notification_triggers_processing(self):
        """Test that receiving a valid webhook notification triggers the processing of the
        payment data."""
        self._create_transaction("direct")
        url = self._build_url(RazorpayController._webhook_url)
        with (
            patch(
                "odoo.addons.payment_razorpay.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
            ),
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ) as process_mock,
        ):
            self._make_json_request(url, data=self.webhook_payment_data)
        self.assertEqual(process_mock.call_count, 1)

    @mute_logger("odoo.addons.payment_razorpay.models.payment_transaction")
    def test_webhook_notification_triggers_signature_check(self):
        """Test that receiving a webhook notification triggers a signature check."""
        self._create_transaction("redirect")
        url = self._build_url(RazorpayController._webhook_url)
        with (
            patch(
                "odoo.addons.payment_razorpay.models.payment_transaction.PaymentTransaction._is_inbound_request_authentic"
            ) as signature_check_mock,
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ),
        ):
            self._make_json_request(url, data=self.webhook_payment_data)
            self.assertEqual(signature_check_mock.call_count, 1)

    def test_accept_webhook_notification_with_valid_signature(self):
        """Test the verification of a webhook notification with a valid signature."""
        tx = self._create_transaction("redirect")
        with patch(
            "odoo.addons.payment_razorpay.models.payment_provider.PaymentProvider"
            "._get_razorpay_signature",
            return_value="valid_signature",
        ):
            self.assertTrue(
                tx._is_razorpay_signature_valid(
                    self.webhook_payment_data, "valid_signature", is_redirect=False
                )
            )

    @mute_logger("odoo.addons.payment_razorpay.models.payment_transaction")
    def test_reject_notification_with_missing_signature(self):
        """Test the verification of a notification with a missing signature."""
        tx = self._create_transaction("redirect")
        self.assertFalse(
            tx._is_razorpay_signature_valid(self.webhook_payment_data, None)
        )

    @mute_logger("odoo.addons.payment_razorpay.models.payment_transaction")
    def test_reject_notification_with_invalid_signature(self):
        """Test the verification of a notification with an invalid signature."""
        tx = self._create_transaction("redirect")
        with patch(
            "odoo.addons.payment_razorpay.models.payment_provider.PaymentProvider"
            "._get_razorpay_signature",
            return_value="valid_signature",
        ):
            self.assertFalse(
                tx._is_razorpay_signature_valid(
                    self.webhook_payment_data, "bad_signature"
                )
            )

    @mute_logger("odoo.addons.payment_razorpay.models.payment_transaction")
    def test_reject_notification_with_a_signature_that_is_no_ascii_string(self):
        """Test that a non-ASCII or non-string signature is refused, not raised on."""
        tx = self._create_transaction("redirect")
        with patch(
            "odoo.addons.payment_razorpay.models.payment_provider.PaymentProvider"
            "._get_razorpay_signature",
            return_value="valid_signature",
        ):
            for signature in ("é" * 15, ["valid_signature"]):
                with self.subTest(signature=signature):
                    self.assertFalse(
                        tx._is_razorpay_signature_valid(
                            self.webhook_payment_data, signature
                        )
                    )

    @mute_logger("odoo.addons.payment_razorpay.models.payment_transaction")
    def test_a_malformed_webhook_body_is_refused_without_a_traceback(self):
        url = self._build_url(RazorpayController._webhook_url)
        for body, status in (
            ("not json", 400),
            ([], 400),
            ({"event": "payment.captured"}, 200),
            ({"event": "payment.captured", "payload": []}, 200),
            ({"event": "payment.captured", "payload": {"payment": "pay_1"}}, 200),
        ):
            with self.subTest(body=body):
                self.assertEqual(
                    self._post_malformed_json(url, body).status_code, status
                )

    @mute_logger("odoo.addons.payment_razorpay.models.payment_transaction")
    def test_a_webhook_whose_references_are_no_strings_is_acknowledged_without_a_traceback(
        self,
    ):
        first = self._create_transaction("direct", reference="ref-1", state="done")
        second = self._create_transaction("direct", reference="ref-2", state="done")
        first.provider_reference, second.provider_reference = "pay_1", "pay_2"
        url = self._build_url(RazorpayController._webhook_url)
        references = [first.reference, second.reference]
        for event, entity in (
            ("payment.captured", {"description": references}),
            ("refund.processed", {"notes": {"reference": references}}),
            ("refund.processed", {"payment_id": ["pay_1", "pay_2"]}),
            ("refund.processed", {"notes": []}),
        ):
            body = {
                "event": event,
                "payload": {event.split(".")[0]: {"entity": entity}},
            }
            with self.subTest(body=body):
                self.assertEqual(self._post_malformed_json(url, body).status_code, 200)

    @mute_logger(
        "odoo.addons.payment_razorpay.controllers.main",
        "odoo.addons.payment_razorpay.models.payment_transaction",
    )
    def test_a_refund_from_razorpay_creates_its_transaction_only_once_the_notification_is_verified(
        self,
    ):
        source_tx = self._create_transaction(
            "direct", state="done", provider_reference=self.payment_id
        )
        body = json_dumps(
            {
                "event": "refund.processed",
                "payload": {
                    "refund": {
                        "entity": {
                            **self.refund_data,
                            "amount": 1000,
                            "status": "processed",
                        }
                    }
                },
            }
        )
        url = self._build_url(RazorpayController._webhook_url)
        children = self.env["payment.transaction"]
        refunds_when_verified = []
        verify_inbound_request = type(children)._is_inbound_request_authentic

        def verify(tx, headers, body):
            refunds_when_verified.append(
                children.search_count([("source_transaction_id", "=", source_tx.id)])
            )
            return verify_inbound_request(tx, headers, body)

        with patch.object(type(children), "_is_inbound_request_authentic", verify):
            for signature in (
                "0" * 64,
                self.provider._get_razorpay_signature(body.encode(), is_redirect=False),
            ):
                with self._assertNoTracebackLogged():
                    self.url_open(
                        url,
                        data=body,
                        headers={
                            "Content-Type": "application/json",
                            "X-Razorpay-Signature": signature,
                        },
                    )
        self.assertEqual(refunds_when_verified, [0, 0])
        refund_tx = children.search([("source_transaction_id", "=", source_tx.id)])
        self.assertEqual(refund_tx.provider_reference, self.refund_id)
        self.assertEqual(refund_tx.operation, "refund")

    @mute_logger(
        "odoo.addons.payment_razorpay.controllers.main",
        "odoo.addons.payment_razorpay.models.payment_transaction",
    )
    def test_a_redelivered_webhook_of_a_refund_from_razorpay_creates_no_second_refund_transaction(
        self,
    ):
        source_tx = self._create_transaction(
            "direct", state="done", provider_reference=self.payment_id
        )
        url = self._build_url(RazorpayController._webhook_url)
        body = json_dumps(
            {
                "event": "refund.processed",
                "payload": {
                    "refund": {
                        "entity": {
                            **self.refund_data,
                            "amount": 1000,
                            "status": "processed",
                        }
                    }
                },
            }
        )
        for _delivery in range(2):
            with self._assertNoTracebackLogged():
                self.url_open(
                    url,
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Razorpay-Signature": self.provider._get_razorpay_signature(
                            body.encode(), is_redirect=False
                        ),
                    },
                )
        refund_tx = self.env["payment.transaction"].search(
            [("source_transaction_id", "=", source_tx.id)]
        )
        self.assertEqual(len(refund_tx), 1)
        self.assertEqual(refund_tx.provider_reference, self.refund_id)
        self.assertEqual(refund_tx.state, "done")
