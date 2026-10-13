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
        field = self.env["delivery.carrier"]._fields["sendcloud_public_key"]

        self.assertTrue(field.store)
        self.assertFalse(field.compute)

    def test_clearing_the_secret_unlinks_the_credential(self):
        credential = self.carrier.carrier_credential_id
        self.assertTrue(credential)

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
        duplicate = self.carrier.copy()

        self.assertEqual(duplicate.sendcloud_secret_key, "a-secret-key")
        self.assertNotEqual(
            duplicate.carrier_credential_id, self.carrier.carrier_credential_id
        )
