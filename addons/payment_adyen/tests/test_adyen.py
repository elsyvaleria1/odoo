from types import SimpleNamespace
from unittest.mock import patch

from odoo import Command, release
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_adyen import utils as adyen_utils
from odoo.addons.payment_adyen.controllers.main import AdyenController
from odoo.addons.payment_adyen.tests.common import AdyenCommon


@tagged("post_install", "-at_install")
class AdyenTest(AdyenCommon, PaymentHttpCommon):
    def test_processing_values(self):
        tx = self._create_transaction(flow="direct")
        with (
            mute_logger("odoo.addons.payment.models.payment_transaction"),
            patch(
                "odoo.addons.payment.utils.request",
                new=SimpleNamespace(env=self.env),
            ),
        ):
            processing_values = tx._prepare_processing_values()

        converted_amount = 111111
        self.assertEqual(
            payment_utils.major_to_minor_currency_units(self.amount, self.currency),
            converted_amount,
        )
        self.assertEqual(processing_values["converted_amount"], converted_amount)
        with patch(
            "odoo.addons.payment.utils.request",
            new=SimpleNamespace(env=self.env),
        ):
            self.assertTrue(
                payment_utils.is_access_token_valid(
                    processing_values["access_token"],
                    self.reference,
                    converted_amount,
                    self.currency.id,
                    self.partner.id,
                )
            )

    @mute_logger("odoo.addons.payment_adyen.models.payment_transaction")
    def test_send_refund_request(self):
        self.provider.support_refund = "full_only"
        tx = self._create_transaction(
            "redirect", state="done", provider_reference="source_reference"
        )
        tx._post_process()

        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
            new=lambda *args, **kwargs: {
                "pspReference": "refund_reference",
                "status": "received",
            },
        ):
            tx._refund()

        refund_tx = self.env["payment.transaction"].search(
            [("source_transaction_id", "=", tx.id)]
        )
        self.assertTrue(
            refund_tx,
            msg="Refunding an Adyen transaction should always create a refund transaction.",
        )
        self.assertTrue(
            refund_tx.state == "draft",
            msg="A refund request as been made, but the state of the refund tx stays as 'draft' "
            "until a success notification is sent",
        )
        self.assertNotEqual(
            refund_tx.provider_reference,
            tx.provider_reference,
            msg="The provider reference of the refund transaction should be different from that of "
            "the source transaction.",
        )

    def test_search_by_reference_returns_refund_tx(self):
        source_tx = self._create_transaction(
            "direct", state="done", provider_reference=self.original_reference
        )
        refund_tx = self._create_transaction(
            "direct",
            reference="RefundTx",
            provider_reference=self.psp_reference,
            amount=-source_tx.amount,
            operation="refund",
            source_transaction_id=source_tx.id,
        )
        data = dict(
            self.webhook_notification_payload,
            amount={
                "currency": self.currency.name,
                "value": payment_utils.major_to_minor_currency_units(
                    source_tx.amount, refund_tx.currency_id
                ),
            },
            eventCode="REFUND",
        )
        returned_tx = self.env["payment.transaction"]._search_by_reference(
            "adyen", data
        )
        self.assertEqual(
            returned_tx, refund_tx, msg="The existing refund tx is the one returned"
        )

    def test_search_by_reference_creates_refund_tx_when_missing(self):
        source_tx = self._create_transaction(
            "direct", state="done", provider_reference=self.original_reference
        )
        data = dict(
            self.webhook_notification_payload,
            amount={
                "currency": self.currency.name,
                "value": payment_utils.major_to_minor_currency_units(
                    self.amount, source_tx.currency_id
                ),
            },
            eventCode="REFUND",
        )
        refund_tx = self.env["payment.transaction"]._search_by_reference("adyen", data)
        self.assertTrue(
            refund_tx,
            msg="If no refund tx is found with received refund data, a refund tx should be created",
        )
        self.assertNotEqual(refund_tx, source_tx)
        self.assertEqual(refund_tx.source_transaction_id, source_tx)

    def test_search_by_reference_returns_partial_capture_child_tx(self):
        self.provider.capture_manually = True
        source_tx = self._create_transaction(
            "direct", state="authorized", provider_reference=self.original_reference
        )
        capture_tx = self._create_transaction(
            "direct",
            reference="CaptureTx",
            provider_reference=self.psp_reference,
            amount=source_tx.amount - 10,
            operation=source_tx.operation,
            source_transaction_id=source_tx.id,
        )
        data = dict(
            self.webhook_notification_payload,
            amount={
                "currency": self.currency.name,
                "value": payment_utils.major_to_minor_currency_units(
                    source_tx.amount - 10, capture_tx.currency_id
                ),
            },
            eventCode="CAPTURE",
        )
        returned_tx = self.env["payment.transaction"]._search_by_reference(
            "adyen", data
        )
        self.assertEqual(
            returned_tx, capture_tx, msg="The existing capture tx is the one returned"
        )

    def test_search_by_reference_creates_capture_tx_when_missing(self):
        self.provider.capture_manually = True
        source_tx = self._create_transaction(
            "direct", state="authorized", provider_reference=self.original_reference
        )
        data = dict(
            self.webhook_notification_payload,
            amount={
                "currency": self.currency.name,
                "value": payment_utils.major_to_minor_currency_units(
                    self.amount - 10, source_tx.currency_id
                ),
            },
            eventCode="CAPTURE",
        )
        capture_tx = self.env["payment.transaction"]._search_by_reference("adyen", data)
        self.assertTrue(
            capture_tx,
            msg="If no child tx is found with received capture data, a child tx should be created.",
        )
        self.assertNotEqual(capture_tx, source_tx)
        self.assertEqual(capture_tx.source_transaction_id, source_tx)

    def test_search_by_reference_returns_void_tx(self):
        self.provider.capture_manually = True
        source_tx = self._create_transaction(
            "direct", state="authorized", provider_reference=self.original_reference
        )
        cancel_tx = self._create_transaction(
            "direct",
            reference="CancelTx",
            provider_reference=self.psp_reference,
            amount=source_tx.amount - 10,
            operation=source_tx.operation,
            source_transaction_id=source_tx.id,
        )
        data = dict(
            self.webhook_notification_payload,
            amount={
                "currency": self.currency.name,
                "value": payment_utils.major_to_minor_currency_units(
                    source_tx.amount - 10, cancel_tx.currency_id
                ),
            },
            eventCode="CANCELLATION",
        )
        returned_tx = self.env["payment.transaction"]._search_by_reference(
            "adyen", data
        )
        self.assertEqual(
            returned_tx, cancel_tx, msg="The existing void tx is the one returned"
        )

    def test_search_by_reference_creates_void_tx_when_missing(self):
        self.provider.capture_manually = True
        source_tx = self._create_transaction(
            "direct", state="authorized", provider_reference=self.original_reference
        )
        data = dict(
            self.webhook_notification_payload,
            amount={
                "currency": self.currency.name,
                "value": payment_utils.major_to_minor_currency_units(
                    self.amount - 10, source_tx.currency_id
                ),
            },
            eventCode="CANCELLATION",
        )
        void_tx = self.env["payment.transaction"]._search_by_reference("adyen", data)
        self.assertTrue(
            void_tx,
            msg="If no child tx is found with received void data, a child tx should be created.",
        )
        self.assertNotEqual(void_tx, source_tx)
        self.assertEqual(void_tx.source_transaction_id, source_tx)

    @mute_logger("odoo.addons.payment_adyen.models.payment_transaction")
    def test_tx_state_after_send_full_capture_request(self):
        self.provider.capture_manually = True
        tx = self._create_transaction("direct", state="authorized")

        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
            return_value={"status": "received"},
        ):
            tx._capture()
        self.assertEqual(
            tx.state,
            "authorized",
            msg="A capture request as been made, but the state of the transaction stays as "
            "'authorized' until a success notification is sent",
        )

    @mute_logger("odoo.addons.payment_adyen.models.payment_transaction")
    def test_tx_state_after_partial_capture_request(self):
        self.provider.capture_manually = True
        tx = self._create_transaction("direct", state="authorized")

        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
            return_value={"status": "received"},
        ):
            tx._capture(amount_to_capture=10)
        self.assertEqual(
            tx.state,
            "authorized",
            msg="A partial capture request as been made, but the state of the source transaction "
            "stays as 'authorized' until the full amount is either done or canceled.",
        )
        self.assertEqual(
            tx.child_transaction_ids[0].state,
            "draft",
            msg="A partial capture request as been made, but the state of the child transaction "
            "stays as 'draft' until a success notification is sent.",
        )

    @mute_logger("odoo.addons.payment_adyen.models.payment_transaction")
    def test_tx_state_after_send_void_request(self):
        self.provider.capture_manually = True
        tx = self._create_transaction("direct", state="authorized")

        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
            return_value={"status": "received"},
        ):
            tx._void()
        self.assertEqual(
            tx.state,
            "authorized",
            msg="A void request as been made, but the state of the transaction stays as"
            " 'authorized' until a success notification is sent",
        )

    def test_extract_token_values_maps_fields_correctly(self):
        tx = self._create_transaction("direct")
        payment_data = {
            "additionalData": {
                "recurring.recurringDetailReference": "token_reference",
                "cardSummary": "4242",
                "recurring.shopperReference": "partner_reference",
            },
        }
        token_values = tx._extract_token_values(payment_data)
        self.assertDictEqual(
            token_values,
            {
                "provider_ref": "token_reference",
                "payment_details": "4242",
                "adyen_shopper_reference": "partner_reference",
            },
        )

    def test_application_info_passed_in_payment_request(self):
        tx = self._create_transaction("direct")
        with (
            patch(
                "odoo.addons.payment.utils.is_access_token_valid",
                return_value="dummy_token",
            ),
            patch(
                "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
                return_value={},
            ) as mock_make_request,
        ):
            self.call_jsonrpc(
                "/payment/adyen/payments",
                params={
                    "provider_id": tx.provider_id.id,
                    "reference": tx.reference,
                    "converted_amount": 1,
                    "currency_id": tx.currency_id.id,
                    "partner_id": tx.partner_id.id,
                    "payment_method": {"type": "scheme"},
                    "access_token": "dummy",
                },
            )
        application_info = mock_make_request.call_args.kwargs["json"].get(
            "applicationInfo"
        )
        self.assertDictEqual(
            application_info,
            {
                "externalPlatform": {
                    "name": "Odoo",
                    "version": release.version,
                    "integrator": "Odoo SA",
                }
            },
        )

    def test_application_info_passed_in_token_payment_request(self):
        tx = self._create_transaction("token", token_id=self._create_token().id)
        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
            return_value={},
        ) as mock_make_request:
            tx._send_payment_request()
        application_info = mock_make_request.call_args.kwargs["json"].get(
            "applicationInfo"
        )
        self.assertDictEqual(
            application_info,
            {
                "externalPlatform": {
                    "name": "Odoo",
                    "version": release.version,
                    "integrator": "Odoo SA",
                }
            },
        )

    def test_webhook_notification_confirms_transaction(self):
        tx = self._create_transaction("direct")
        self._webhook_notification_flow(self.webhook_notification_batch_data)
        self.assertEqual(tx.state, "done")

    def test_webhook_notification_authorizes_transaction(self):
        self.provider.capture_manually = True
        tx = self._create_transaction("direct")
        self._webhook_notification_flow(self.webhook_notification_batch_data)
        self.assertEqual(
            tx.state,
            "authorized",
            msg="The authorization succeeded, the manual capture is enabled, the tx state should be"
            " 'authorized'.",
        )

    def test_webhook_notification_captures_transaction(self):
        self.provider.capture_manually = True
        tx = self._create_transaction(
            "direct",
            state="authorized",
            provider_reference=self.original_reference,
            amount=9.99,
        )
        payload = dict(
            self.webhook_notification_batch_data,
            notificationItems=[
                {
                    "NotificationRequestItem": dict(
                        self.webhook_notification_payload,
                        amount={
                            "currency": self.currency.name,
                            "value": payment_utils.major_to_minor_currency_units(
                                9.99, tx.currency_id
                            ),
                        },
                        eventCode="CAPTURE",
                    )
                }
            ],
        )
        self._webhook_notification_flow(payload)
        self.assertEqual(
            tx.state,
            "done",
            msg="The capture succeeded, the tx state should be 'done'.",
        )

    def test_webhook_notification_cancels_transaction(self):
        tx = self._create_transaction(
            "direct",
            state="pending",
            provider_reference=self.original_reference,
            amount=9.99,
        )
        payload = dict(
            self.webhook_notification_batch_data,
            notificationItems=[
                {
                    "NotificationRequestItem": dict(
                        self.webhook_notification_payload,
                        amount={
                            "currency": self.currency.name,
                            "value": payment_utils.major_to_minor_currency_units(
                                9.99, tx.currency_id
                            ),
                        },
                        eventCode="CANCELLATION",
                    )
                }
            ],
        )
        self._webhook_notification_flow(payload)
        self.assertEqual(
            tx.state,
            "cancel",
            msg="The cancellation succeeded, the tx state should be 'cancel'.",
        )

    def test_webhook_notification_refunds_transaction(self):
        source_tx = self._create_transaction(
            "direct", state="done", provider_reference=self.original_reference
        )
        payload = dict(
            self.webhook_notification_batch_data,
            notificationItems=[
                {
                    "NotificationRequestItem": dict(
                        self.webhook_notification_payload,
                        amount={
                            "currency": self.currency.name,
                            "value": payment_utils.major_to_minor_currency_units(
                                self.amount, source_tx.currency_id
                            ),
                        },
                        eventCode="REFUND",
                    )
                }
            ],
        )
        self._webhook_notification_flow(payload)
        refund_tx = self.env["payment.transaction"].search(
            [("source_transaction_id", "=", source_tx.id)]
        )
        self.assertEqual(
            refund_tx.state,
            "done",
            msg="After a successful refund notification, the refund state should be in 'done'.",
        )

    def test_failed_webhook_authorization_notification_leaves_transaction_in_draft(
        self,
    ):
        tx = self._create_transaction("direct")
        payload = dict(
            self.webhook_notification_batch_data,
            notificationItems=[
                {
                    "NotificationRequestItem": dict(
                        self.webhook_notification_payload, success="false"
                    )
                }
            ],
        )
        self._webhook_notification_flow(payload)
        self.assertEqual(
            tx.state,
            "draft",
            msg="The authorization failed, as we don't support failed authorization, the tx state "
            "should still be 'draft'.",
        )

    def test_failed_webhook_capture_notification_leaves_transaction_authorized(self):
        tx = self._create_transaction(
            "direct", state="authorized", provider_reference=self.original_reference
        )
        payload = dict(
            self.webhook_notification_batch_data,
            notificationItems=[
                {
                    "NotificationRequestItem": dict(
                        self.webhook_notification_payload,
                        eventCode="CAPTURE",
                        success="false",
                    )
                }
            ],
        )
        self._webhook_notification_flow(payload)
        self.assertEqual(
            tx.state,
            "authorized",
            msg="The capture failed, the tx state should still be 'authorized'.",
        )

    def test_failed_webhook_cancellation_notification_leaves_transaction_authorized(
        self,
    ):
        tx = self._create_transaction("direct", state="authorized")
        payload = dict(
            self.webhook_notification_batch_data,
            notificationItems=[
                {
                    "NotificationRequestItem": dict(
                        self.webhook_notification_payload,
                        eventCode="CANCELLATION",
                        success="false",
                    )
                }
            ],
        )
        self._webhook_notification_flow(payload)
        self.assertEqual(
            tx.state,
            "authorized",
            msg="The cancellation failed, the tx state should still be 'authorized'.",
        )

    def test_failed_webhook_refund_notification_sets_refund_transaction_in_error(self):
        source_tx = self._create_transaction(
            "direct", state="done", provider_reference=self.original_reference
        )
        payload = dict(
            self.webhook_notification_batch_data,
            notificationItems=[
                {
                    "NotificationRequestItem": dict(
                        self.webhook_notification_payload,
                        amount={
                            "currency": self.currency.name,
                            "value": payment_utils.major_to_minor_currency_units(
                                self.amount, source_tx.currency_id
                            ),
                        },
                        eventCode="REFUND",
                        success="false",
                    )
                }
            ],
        )
        self._webhook_notification_flow(payload)
        refund_tx = self.env["payment.transaction"].search(
            [("source_transaction_id", "=", source_tx.id)]
        )
        self.assertEqual(
            refund_tx.state,
            "error",
            msg="After a failed refund notification, the refund state should be in 'error'.",
        )

    @mute_logger("odoo.addons.payment_adyen.controllers.main")
    @mute_logger("odoo.addons.payment_adyen.models.payment_transaction")
    def _webhook_notification_flow(self, payload):
        url = self._build_url(AdyenController._webhook_url)
        with patch(
            "odoo.addons.payment_adyen.models.payment_provider.PaymentProvider._is_inbound_request_authentic"
        ):
            response = self._make_json_request(url, data=payload).json()
        self.assertEqual(
            response,
            "[accepted]",
            msg="The webhook should always respond '[accepted]'",
        )

    @mute_logger("odoo.addons.payment_adyen.controllers.main")
    def test_webhook_notification_triggers_signature_check(self):
        self._create_transaction("direct")
        url = self._build_url(AdyenController._webhook_url)
        with (
            patch(
                "odoo.addons.payment_adyen.models.payment_provider.PaymentProvider._is_inbound_request_authentic"
            ) as signature_check_mock,
            patch(
                "odoo.addons.payment.models.payment_transaction.PaymentTransaction._process"
            ),
        ):
            self._make_json_request(url, data=self.webhook_notification_batch_data)
            self.assertEqual(signature_check_mock.call_count, 1)

    def test_accept_webhook_notification_with_valid_signature(self):
        tx = self._create_transaction("direct")
        self.assertTrue(
            tx.provider_id._is_adyen_notification_item_signature_valid(
                self.webhook_notification_payload
            )
        )

    @mute_logger("odoo.addons.payment_adyen.models.payment_provider")
    def test_reject_webhook_notification_with_missing_signature(self):
        payload = dict(
            self.webhook_notification_payload, additionalData={"hmacSignature": None}
        )
        tx = self._create_transaction("direct")
        self.assertFalse(
            tx.provider_id._is_adyen_notification_item_signature_valid(payload)
        )

    @mute_logger("odoo.addons.payment_adyen.models.payment_provider")
    def test_reject_webhook_notification_with_invalid_signature(self):
        payload = dict(
            self.webhook_notification_payload, additionalData={"hmacSignature": "dummy"}
        )
        tx = self._create_transaction("direct")
        self.assertFalse(
            tx.provider_id._is_adyen_notification_item_signature_valid(payload)
        )

    @mute_logger("odoo.addons.payment_adyen.models.payment_transaction")
    def test_no_information_missing_from_partner_address(self):
        test_partner = self.env["res.partner"].create(
            {
                "name": "Dummy Partner",
                "email": "norbert.buyer@example.com",
                "phone_ids": [Command.create({"number": "0032 12 34 56 78"})],
            }
        )
        test_address = adyen_utils.format_partner_address(test_partner)
        for key in (
            "city",
            "country",
            "stateOrProvince",
            "street",
        ):
            self.assertTrue(test_address.get(key))

    @mute_logger("odoo.addons.payment_adyen.models.payment_provider")
    def test_reject_webhook_notification_with_a_signature_that_is_no_ascii_string(
        self,
    ):
        tx = self._create_transaction("direct")
        for signature in ("é" * 44, ["dummy"], 42):
            with self.subTest(signature=signature):
                payload = dict(
                    self.webhook_notification_payload,
                    additionalData={"hmacSignature": signature},
                )
                self.assertFalse(
                    tx.provider_id._is_adyen_notification_item_signature_valid(payload)
                )

    @mute_logger(
        "odoo.addons.payment_adyen.models.payment_provider",
        "odoo.addons.payment_adyen.models.payment_transaction",
    )
    def test_a_webhook_whose_body_is_no_notification_batch_is_refused_without_a_traceback(
        self,
    ):
        self._create_transaction("direct")
        url = self._build_url(AdyenController._webhook_url)
        unsigned_item = dict(self.webhook_notification_payload, additionalData=[])
        for body, status in (
            ("not json", 400),
            ([], 400),
            ({"notificationItems": {}}, 400),
            ({"notificationItems": ["item"]}, 400),
            ({"notificationItems": [{"NotificationRequestItem": []}]}, 400),
            ({"notificationItems": [{"NotificationRequestItem": unsigned_item}]}, 401),
        ):
            with self.subTest(body=body):
                self.assertEqual(
                    self._post_malformed_json(url, body).status_code, status
                )

    @mute_logger("odoo.addons.payment_adyen.models.payment_transaction")
    def test_a_merchant_reference_that_is_no_string_finds_no_transaction(self):
        first = self._create_transaction("direct", reference="ref-1")
        second = self._create_transaction("direct", reference="ref-2")
        data = dict(
            self.webhook_notification_payload,
            merchantReference=[first.reference, second.reference],
        )
        self.assertFalse(
            self.env["payment.transaction"]._search_by_reference("adyen", data)
        )

    @mute_logger(
        "odoo.addons.payment_adyen.models.payment_provider",
        "odoo.addons.payment_adyen.models.payment_transaction",
    )
    def test_a_notification_without_original_reference_is_acknowledged_without_a_traceback(
        self,
    ):
        for reference in ("ref-1", "ref-2"):
            self._create_transaction(
                "direct", reference=reference, state="authorized"
            ).provider_reference = False
        url = self._build_url(AdyenController._webhook_url)
        for event_code in ("CAPTURE", "CANCELLATION", "REFUND"):
            item = dict(self.webhook_notification_payload, eventCode=event_code)
            del item["originalReference"]
            with self.subTest(event_code=event_code):
                response = self._post_malformed_json(
                    url, {"notificationItems": [{"NotificationRequestItem": item}]}
                )
                self.assertEqual(response.json(), "[accepted]")

    @mute_logger(
        "odoo.addons.payment_adyen.controllers.main",
        "odoo.addons.payment_adyen.models.payment_transaction",
    )
    def test_a_signed_capture_or_void_whose_amount_is_no_integer_changes_nothing(self):
        source_tx = self._create_transaction(
            "direct", state="authorized", provider_reference=self.original_reference
        )
        url = self._build_url(AdyenController._webhook_url)
        for event_code in ("CAPTURE", "CANCELLATION"):
            for amount in (
                {"currency": self.currency.name, "value": "1111"},
                {"currency": self.currency.name, "value": 11.11},
                {"currency": self.currency.name, "value": True},
                {"currency": self.currency.name, "value": [1111]},
                {"currency": self.currency.name},
                [],
                "1111",
            ):
                item = dict(
                    self.webhook_notification_payload,
                    eventCode=event_code,
                    amount=amount,
                )
                item["additionalData"] = {
                    "hmacSignature": adyen_utils.compute_notification_signature(
                        item, self.adyen.adyen_hmac_key
                    )
                }
                with self.subTest(event_code=event_code, amount=amount):
                    response = self._post_malformed_json(
                        url, {"notificationItems": [{"NotificationRequestItem": item}]}
                    )
                    self.assertEqual(response.json(), "[accepted]")
        self.assertEqual(source_tx.state, "authorized")
        self.assertFalse(source_tx.child_transaction_ids)

    @mute_logger(
        "odoo.addons.payment_adyen.controllers.main",
        "odoo.addons.payment_adyen.models.payment_provider",
        "odoo.addons.payment_adyen.models.payment_transaction",
    )
    def test_a_partial_capture_creates_its_transaction_only_once_the_notification_is_verified(
        self,
    ):
        self.provider.capture_manually = True
        source_tx = self._create_transaction(
            "direct", state="authorized", provider_reference=self.original_reference
        )
        item = dict(
            self.webhook_notification_payload,
            eventCode="CAPTURE",
            amount={
                "currency": self.currency.name,
                "value": payment_utils.major_to_minor_currency_units(
                    source_tx.amount - 10, source_tx.currency_id
                ),
            },
        )
        url = self._build_url(AdyenController._webhook_url)
        children = self.env["payment.transaction"].with_context(active_test=False)
        children_when_verified = []
        verify_inbound_request = type(self.provider)._is_inbound_request_authentic

        def verify(provider, headers, body):
            children_when_verified.append(
                children.search_count([("source_transaction_id", "=", source_tx.id)])
            )
            return verify_inbound_request(provider, headers, body)

        with patch.object(type(self.provider), "_is_inbound_request_authentic", verify):
            response = self._make_json_request(
                url, data={"notificationItems": [{"NotificationRequestItem": item}]}
            )
            self.assertEqual(response.status_code, 401)
            item["additionalData"] = {
                "hmacSignature": adyen_utils.compute_notification_signature(
                    item, self.adyen.adyen_hmac_key
                )
            }
            response = self._make_json_request(
                url, data={"notificationItems": [{"NotificationRequestItem": item}]}
            )
            self.assertEqual(response.json(), "[accepted]")
        self.assertEqual(children_when_verified, [0, 0])
        capture_tx = children.search([("source_transaction_id", "=", source_tx.id)])
        self.assertEqual(capture_tx.amount, source_tx.amount - 10)
        self.assertEqual(capture_tx.state, "done")

    def test_a_full_capture_in_a_currency_with_adyen_specific_decimals_resolves_the_source_transaction(
        self,
    ):
        clp = self.env.ref("base.CLP")
        clp.active = True
        source_tx = self._create_transaction(
            "direct",
            state="authorized",
            provider_reference=self.original_reference,
            amount=1000,
            currency_id=clp.id,
        )
        data = dict(
            self.webhook_notification_payload,
            eventCode="CAPTURE",
            amount={"currency": clp.name, "value": 100000},
        )
        self.assertEqual(
            self.env["payment.transaction"]._search_by_reference("adyen", data),
            source_tx,
        )

    @mute_logger("odoo.addons.payment_adyen.controllers.main")
    def test_a_return_without_a_redirect_result_shows_the_status_page(self):
        tx = self._create_transaction("direct")
        with self._assertNoTracebackLogged():
            response = self.url_open(
                self._build_url("/payment/adyen/return"),
                params={"merchantReference": tx.reference},
                allow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/payment/status"))
        self.assertEqual(tx.operation, "online_direct")

    @mute_logger(
        "odoo.addons.payment_adyen.controllers.main",
        "odoo.addons.payment_adyen.models.payment_transaction",
    )
    def test_a_signed_notification_of_an_unhandled_event_creates_no_child_transaction(
        self,
    ):
        source_tx = self._create_transaction(
            "direct", state="done", provider_reference=self.original_reference
        )
        url = self._build_url(AdyenController._webhook_url)
        for event_code, success in (
            ("CANCEL_OR_REFUND", "true"),
            ("TECHNICAL_CANCEL", "true"),
            ("CAPTURE_FAILED", "false"),
        ):
            item = dict(
                self.webhook_notification_payload,
                eventCode=event_code,
                success=success,
            )
            item["additionalData"] = {
                "hmacSignature": adyen_utils.compute_notification_signature(
                    item, self.adyen.adyen_hmac_key
                )
            }
            with self.subTest(event_code=event_code):
                response = self._post_malformed_json(
                    url, {"notificationItems": [{"NotificationRequestItem": item}]}
                )
                self.assertEqual(response.json(), "[accepted]")
        self.assertFalse(source_tx.child_transaction_ids)

    @mute_logger("odoo.addons.payment_adyen.models.payment_transaction")
    def test_a_child_operation_whose_provider_references_are_no_strings_finds_and_creates_nothing(
        self,
    ):
        self.provider.capture_manually = True
        for reference in ("ref-1", "ref-2"):
            self._create_transaction(
                "direct", reference=reference, state="authorized"
            ).provider_reference = False
        for reference in ("psp-1", "psp-2"):
            self._create_transaction(
                "direct", reference=reference, provider_reference=reference
            )
        source_tx = self._create_transaction(
            "direct", state="authorized", provider_reference=self.original_reference
        )
        partial_amount = {
            "currency": self.currency.name,
            "value": payment_utils.major_to_minor_currency_units(
                source_tx.amount - 10, source_tx.currency_id
            ),
        }
        transactions = self.env["payment.transaction"]
        count = transactions.search_count([])
        for event_code, references in (
            ("CAPTURE", {"originalReference": None}),
            ("CANCELLATION", {"originalReference": None}),
            ("REFUND", {"originalReference": None, "pspReference": None}),
            ("CAPTURE", {"pspReference": ["psp-1", "psp-2"]}),
            ("REFUND", {"pspReference": ["psp-1", "psp-2"]}),
        ):
            data = dict(
                self.webhook_notification_payload,
                eventCode=event_code,
                amount=partial_amount,
                **references,
            )
            for key in [key for key, value in references.items() if value is None]:
                del data[key]
            with self.subTest(event_code=event_code, references=references):
                self.assertFalse(transactions._search_by_reference("adyen", data))
        self.assertEqual(transactions.search_count([]), count)

    @mute_logger("odoo.addons.payment_adyen.models.payment_transaction")
    def test_a_refund_whose_amount_is_no_integer_creates_no_refund_transaction(self):
        source_tx = self._create_transaction(
            "direct", state="done", provider_reference=self.original_reference
        )
        for amount in (
            {"currency": self.currency.name, "value": "1111"},
            {"currency": self.currency.name, "value": 11.11},
            {"currency": self.currency.name, "value": True},
            {"currency": self.currency.name},
            [],
            "1111",
        ):
            data = dict(
                self.webhook_notification_payload,
                eventCode="REFUND",
                pspReference="refund-psp",
                amount=amount,
            )
            with self.subTest(amount=amount):
                self.assertFalse(
                    self.env["payment.transaction"]._search_by_reference("adyen", data)
                )
        self.assertFalse(source_tx.child_transaction_ids)

    def test_a_partial_capture_in_a_currency_with_adyen_specific_decimals_creates_its_transaction_with_them(
        self,
    ):
        self.provider.capture_manually = True
        clp = self.env.ref("base.CLP")
        clp.active = True
        source_tx = self._create_transaction(
            "direct",
            state="authorized",
            provider_reference=self.original_reference,
            amount=1000,
            currency_id=clp.id,
        )
        data = dict(
            self.webhook_notification_payload,
            eventCode="CAPTURE",
            amount={"currency": clp.name, "value": 40000},
        )
        capture_tx = self.env["payment.transaction"]._search_by_reference("adyen", data)
        self.assertEqual(capture_tx.source_transaction_id, source_tx)
        self.assertEqual(capture_tx.amount, 400)

    @mute_logger(
        "odoo.addons.payment_adyen.controllers.main",
        "odoo.addons.payment_adyen.models.payment_transaction",
    )
    def test_a_return_resolves_the_transaction_its_merchant_reference_names_whatever_event_it_claims(
        self,
    ):
        tx = self._create_transaction(
            "direct", provider_reference=self.original_reference
        )
        other_tx = self._create_transaction(
            "direct", reference="other", provider_reference="other-psp"
        )
        with patch(
            "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
            return_value={},
        ):
            response = self.url_open(
                self._build_url("/payment/adyen/return"),
                params={
                    "merchantReference": tx.reference,
                    "redirectResult": "result",
                    "eventCode": "REFUND",
                    "pspReference": other_tx.provider_reference,
                },
                allow_redirects=False,
            )
        self.assertEqual(response.status_code, 303)
        self.assertEqual(tx.operation, "online_redirect")
        self.assertEqual(other_tx.operation, "online_direct")

    @mute_logger("odoo.addons.payment_adyen.models.payment_provider")
    def test_a_child_operation_whose_merchant_reference_is_no_string_is_acknowledged_unverified(
        self,
    ):
        self._create_transaction(
            "direct", state="authorized", provider_reference=self.original_reference
        )
        url = self._build_url(AdyenController._webhook_url)
        for event_code in ("CAPTURE", "CANCELLATION", "REFUND"):
            item = dict(
                self.webhook_notification_payload,
                eventCode=event_code,
                merchantReference=[self.reference],
            )
            with self.subTest(event_code=event_code):
                response = self._post_malformed_json(
                    url, {"notificationItems": [{"NotificationRequestItem": item}]}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), "[accepted]")
