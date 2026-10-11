import time
from datetime import datetime
from unittest.mock import patch

from dateutil.relativedelta import relativedelta

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment_razorpay.tests.common import RazorpayCommon


@tagged("post_install", "-at_install")
class TestPaymentTransaction(RazorpayCommon):
    def test_no_item_missing_from_order_request_payload(self):
        inr_currency = (
            self.env["res.currency"]
            .with_context(active_test=False)
            .search(
                [
                    ("name", "=", "INR"),
                ],
                limit=1,
            )
        )
        tx = self._create_transaction("direct", currency_id=inr_currency.id)
        for tokenize in (False, True):
            tx.tokenize = tokenize
            request_payload = tx._razorpay_prepare_order_payload(
                customer_id=self.customer_id
            )
            self.maxDiff = 10000
            converted_amount = payment_utils.major_to_minor_currency_units(
                tx.amount, tx.currency_id
            )
            expected_payload = {
                "amount": converted_amount,
                "currency": tx.currency_id.name,
                "customer_id": self.customer_id,
                "method": "card",
            }
            if tokenize:
                token_expiry_date = datetime.today() + relativedelta(years=10)
                token_expiry_timestamp = time.mktime(token_expiry_date.timetuple())
                expected_payload["token"] = {
                    "expire_at": token_expiry_timestamp,
                    "frequency": "as_presented",
                    "max_amount": 100000000,
                }
            self.assertDictEqual(request_payload, expected_payload)

    def test_void_is_not_supported(self):
        tx = self._create_transaction("direct", state="authorized")
        self.assertRaises(UserError, func=tx._void)

    def test_prevent_multi_payments_on_recurring_transactions(self):
        shared_token = self._create_token()
        self._create_transaction(
            "token", reference="INV123", token_id=shared_token.id, state="pending"
        )
        tx2 = self._create_transaction(
            "token", reference="INV123-1", token_id=shared_token.id
        )
        tx2._charge_with_token()
        self.assertEqual(tx2.state, "error")

    def test_allow_multi_payments_on_non_recurring_transactions(self):
        shared_token = self._create_token(provider_ref="cust_123,token_404")
        different_token = self._create_token(provider_ref="cust_123,token_405")
        tx1 = self._create_transaction(
            "token", reference="INV123", token_id=shared_token.id
        )
        all_states = ["draft", "pending", "done", "cancel", "error"]
        other_txs = [
            self._create_transaction(
                "token", reference="INV456", token_id=shared_token.id
            ),
            self._create_transaction(
                "token", reference="INV123-1", token_id=different_token.id
            ),
        ]
        for state in all_states:
            tx1.state = state
            for other_tx in other_txs:
                converted_amount = payment_utils.major_to_minor_currency_units(
                    other_tx.amount, other_tx.currency_id
                )
                with patch(
                    "odoo.addons.payment.models.payment_provider.PaymentProvider._send_api_request",
                    return_value={
                        "status": "created",
                        "id": "12345",
                        "amount": converted_amount,
                        "currency": other_tx.currency_id.name,
                    },
                ):
                    self._assert_does_not_raise(
                        UserError, other_tx._send_payment_request
                    )
                other_tx.state = "draft"

    def test_search_by_reference_returns_refund_tx(self):
        refund_tx = self._create_transaction("direct")
        returned_tx = self.env["payment.transaction"]._search_by_reference(
            "razorpay",
            dict(
                self.refund_data,
                entity_type="refund",
                notes={
                    "reference": refund_tx.reference,
                },
            ),
        )
        self.assertEqual(returned_tx, refund_tx)

    def test_search_by_reference_creates_refund_tx_when_missing(self):
        source_tx = self._create_transaction(
            "direct", state="done", provider_reference=self.payment_id
        )
        refund_tx = self.env["payment.transaction"]._search_by_reference(
            "razorpay", dict(self.refund_data, entity_type="refund")
        )
        self.assertTrue(
            refund_tx,
            msg="If no refund tx is found with the refund data, a refund tx should be created.",
        )
        self.assertNotEqual(refund_tx, source_tx)
        self.assertEqual(refund_tx.source_transaction_id, source_tx)

    def test_apply_updates_confirms_transaction(self):
        tx = self._create_transaction("direct")
        tx._apply_updates(self.payment_data)
        self.assertEqual(tx.state, "done")

    @mute_logger("odoo.addons.payment.models.payment_transaction")
    @mute_logger("odoo.addons.payment_razorpay.models.payment_transaction")
    def test_apply_updates_updates_reference_if_not_confirmed(self):
        upi = self.env.ref("payment.payment_method_upi")
        tx = self._create_transaction(
            "direct",
            state="done",
            provider_reference=self.payment_id,
            payment_method_id=upi.id,
        )
        tx._apply_updates(self.payment_fail_data)
        self.assertEqual(
            tx.provider_reference,
            self.payment_id,
            msg="The provider reference should not be updated if the transaction is already"
            " confirmed.",
        )
        self.assertEqual(
            tx.payment_method_id,
            upi,
            msg="The payment method should not be updated if the transaction is already confirmed.",
        )

    def test_extract_token_values_maps_fields_correctly(self):
        tx = self._create_transaction("direct")
        token_values = tx._extract_token_values(self.tokenize_payment_data)
        self.assertDictEqual(
            token_values,
            {
                "payment_details": None,
                "provider_ref": f"{self.customer_id},{self.token_id}",
            },
        )

    def test_token_values_not_extracted_if_token_already_exists(self):
        tx = self._create_transaction("direct")
        tx.token_id = self._create_token()
        token_values = tx._extract_token_values(self.tokenize_payment_data)
        self.assertFalse(token_values)
