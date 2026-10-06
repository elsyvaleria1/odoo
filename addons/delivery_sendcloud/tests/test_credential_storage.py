"""Sendcloud credentials are stored in the vault and exposed through field accessors."""

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestSendcloudCredentials(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        product = cls.env["product.product"].create(
            {"name": "Sendcloud Delivery", "type": "service"}
        )
        # Both keys at create: `_check_sendcloud_api_keys` requires them, and it
        # reads the secret through the door -- so this create also proves the
        # inverse has flushed before the constraint runs.
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Sendcloud Probe",
                "delivery_type": "sendcloud",
                "product_id": product.id,
                "sendcloud_public_key": "a-public-key",
                "sendcloud_secret_key": "a-secret-key",
            }
        )

    def test_creating_with_a_secret_creates_a_credential(self):
        self.assertTrue(self.carrier.carrier_credential_id)
        self.assertEqual(
            self.carrier.carrier_credential_id.sudo().api_secret, "a-secret-key"
        )

    def test_the_constraint_reads_the_secret_through_the_door(self):
        # `_check_sendcloud_api_keys` fires on create and on write, and the
        # value it checks now lives in the vault. If the inverse had not flushed
        # before the constraint ran, setUpClass could not have created this
        # carrier at all -- so its existence is half the assertion.
        with self.assertRaises(ValidationError):
            self.env["delivery.carrier"].create(
                {
                    "name": "Sendcloud No Secret",
                    "delivery_type": "sendcloud",
                    "product_id": self.carrier.product_id.id,
                    "sendcloud_public_key": "a-public-key",
                }
            )

    def test_the_field_reads_back_what_was_written(self):
        self.carrier.sendcloud_secret_key = "round-trip"
        self.carrier.invalidate_recordset()

        self.assertEqual(self.carrier.sendcloud_secret_key, "round-trip")

    def test_the_public_key_stays_a_plain_column(self):
        # It is half of a pair and is not a secret, which is why only its
        # sibling was ever on the ADR-0081 backlog.
        field = self.env["delivery.carrier"]._fields["sendcloud_public_key"]

        self.assertTrue(field.store)
        self.assertFalse(field.compute)

    def test_clearing_the_secret_unlinks_the_credential(self):
        credential = self.carrier.carrier_credential_id
        self.assertTrue(credential)

        # Cleared together with the type, or the constraint refuses the write.
        self.carrier.write({"delivery_type": "fixed", "sendcloud_secret_key": False})

        self.assertFalse(self.carrier.carrier_credential_id)
        self.assertFalse(credential.exists())

    def test_no_plaintext_column_survives(self):
        self.env.cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'delivery_carrier'
               AND column_name = 'sendcloud_secret_key'
            """
        )
        self.assertEqual(
            self.env.cr.fetchall(),
            [],
            "the migration drops the column; a nulled one still sits in every "
            "backup taken before it was nulled",
        )

    def test_a_carrier_can_be_duplicated_with_its_secret(self):
        # `_check_sendcloud_api_keys` runs inside the copy's create, so a copy
        # that dropped the secret could not be made at all.
        duplicate = self.carrier.copy()

        self.assertEqual(duplicate.sendcloud_secret_key, "a-secret-key")
        self.assertNotEqual(
            duplicate.carrier_credential_id, self.carrier.carrier_credential_id
        )
