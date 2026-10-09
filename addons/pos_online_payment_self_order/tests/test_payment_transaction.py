from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPaymentTransaction(TransactionCase):
    def test_processing_data_that_names_no_transaction_processes_nothing(self):
        for payment_data in ({"reference": "no-such-transaction"}, {}):
            with self.subTest(payment_data=payment_data):
                self.assertFalse(
                    self.env["payment.transaction"]._process("demo", payment_data)
                )
