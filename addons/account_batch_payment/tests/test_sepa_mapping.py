from odoo.tests.common import TransactionCase

from odoo.addons.account_batch_payment.models.sepa_mapping import (
    normalize_communication,
)


class TestSepaMapping(TransactionCase):
    def test_sepa_mapping(self):
        self.assertEqual(normalize_communication("Hello/world", 5), "Hello")
        self.assertEqual(normalize_communication("Hello / World"), "Hello / World")
        self.assertEqual(normalize_communication("Hello // World"), "Hello / World")
        self.assertEqual(
            normalize_communication("Hello //// W//orld"), "Hello / W/orld"
        )
        self.assertEqual(normalize_communication("/Hello / World/"), "Hello / World")
        self.assertEqual(normalize_communication("Hello / World /"), "Hello / World ")
        self.assertEqual(normalize_communication("\u1f9e/Hello"), "Hello")
        self.assertEqual(normalize_communication("Hello/\u1f9e"), "Hello")
        self.assertEqual(normalize_communication("Hello/\u1f9e/ World"), "Hello/ World")
