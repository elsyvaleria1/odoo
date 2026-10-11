from unittest.mock import patch

from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.payment.tests.http_common import PaymentHttpCommon
from odoo.addons.payment_demo.tests.common import PaymentDemoCommon


@tagged("-at_install", "post_install")
class TestPaymentTransaction(PaymentDemoCommon, PaymentHttpCommon):
    def test_apply_updates_sets_transaction_pending(self):
        tx = self._create_transaction("direct")
        tx._apply_updates(dict(self.payment_data, simulated_state="pending"))
        self.assertEqual(tx.state, "pending")

    def test_apply_updates_authorizes_transaction(self):
        self.provider.capture_manually = True
        tx = self._create_transaction("direct")
        tx._apply_updates(self.payment_data)
        self.assertEqual(tx.state, "authorized")

    def test_apply_updates_confirms_transaction(self):
        tx = self._create_transaction("direct")
        tx._apply_updates(self.payment_data)
        self.assertEqual(tx.state, "done")

    def test_apply_updates_cancels_transaction(self):
        tx = self._create_transaction("direct")
        tx._apply_updates(dict(self.payment_data, simulated_state="cancel"))
        self.assertEqual(tx.state, "cancel")

    def test_apply_updates_sets_transaction_in_error(self):
        tx = self._create_transaction("direct")
        tx._apply_updates(dict(self.payment_data, simulated_state="error"))
        self.assertEqual(tx.state, "error")

    def test_apply_updates_tokenizes_transaction(self):
        tx = self._create_transaction("direct", tokenize=True)
        with patch(
            "odoo.addons.payment.models.payment_transaction.PaymentTransaction._tokenize"
        ) as tokenize_mock:
            tx._apply_updates(self.payment_data)
        self.assertEqual(tokenize_mock.call_count, 1)

    @mute_logger("odoo.addons.payment_demo.models.payment_transaction")
    def test_apply_updates_propagates_simulated_state_to_token(self):
        for counter, state in enumerate(["pending", "done", "cancel", "error"]):
            tx = self._create_transaction(
                "direct", reference=f"{self.reference}-{counter}", tokenize=True
            )
            tx._apply_updates(dict(self.payment_data, simulated_state=state))
            self.assertEqual(tx.token_id.demo_simulated_state, state)

    def test_making_a_payment_request_propagates_token_simulated_state_to_transaction(
        self,
    ):
        for counter, state in enumerate(["pending", "done", "cancel", "error"]):
            tx = self._create_transaction(
                "direct", reference=f"{self.reference}-{counter}"
            )
            tx.token_id = self._create_token(demo_simulated_state=state)
            tx._charge_with_token()
            self.assertEqual(tx.state, tx.token_id.demo_simulated_state)
