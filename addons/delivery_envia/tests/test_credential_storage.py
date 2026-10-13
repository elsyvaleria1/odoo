from odoo.libs.json import loads as json_loads
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestEnviaCredentials(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        product = cls.env["product.product"].create(
            {"name": "Envia Delivery", "type": "service"}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Envia Probe",
                "delivery_type": "envia",
                "product_id": product.id,
            }
        )

    def test_both_keys_live_in_one_credential(self):
        self.carrier.write(
            {
                "envia_sandbox_api_key": "a-test-key",
                "envia_production_api_key": "a-prod-key",
            }
        )
        self.carrier.invalidate_recordset()

        credential = self.carrier.carrier_credential_id.sudo()
        self.assertTrue(credential)
        data = json_loads(credential.credential_data or "{}")
        self.assertEqual(data["envia_sandbox_api_key"], "a-test-key")
        self.assertEqual(data["envia_production_api_key"], "a-prod-key")

    def test_the_fields_read_back_what_was_written(self):
        self.carrier.write(
            {
                "envia_sandbox_api_key": "round-test",
                "envia_production_api_key": "round-prod",
            }
        )
        self.carrier.invalidate_recordset()

        self.assertEqual(self.carrier.envia_sandbox_api_key, "round-test")
        self.assertEqual(self.carrier.envia_production_api_key, "round-prod")

    def test_writing_one_environment_leaves_the_other_alone(self):
        self.carrier.write(
            {
                "envia_sandbox_api_key": "keep-test",
                "envia_production_api_key": "first-prod",
            }
        )

        self.carrier.envia_production_api_key = "second-prod"
        self.carrier.invalidate_recordset()

        self.assertEqual(self.carrier.envia_production_api_key, "second-prod")
        self.assertEqual(self.carrier.envia_sandbox_api_key, "keep-test")

    def test_neither_key_lands_in_a_native_vault_field(self):
        self.carrier.envia_sandbox_api_key = "not-an-api-key"

        credential = self.carrier.carrier_credential_id.sudo()
        self.assertFalse(credential.api_key)
        self.assertFalse(credential.api_secret)

    def test_clearing_both_unlinks_the_credential(self):
        self.carrier.write(
            {
                "envia_sandbox_api_key": "gone-test",
                "envia_production_api_key": "gone-prod",
            }
        )
        credential = self.carrier.carrier_credential_id

        self.carrier.write(
            {
                "envia_sandbox_api_key": False,
                "envia_production_api_key": False,
            }
        )

        self.assertFalse(self.carrier.carrier_credential_id)
        self.assertFalse(credential.exists())

    def test_no_plaintext_column_survives(self):
        self.env.cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'delivery_carrier'
               AND column_name IN ('envia_sandbox_api_key',
                                   'envia_production_api_key')
            """
        )
        self.assertEqual(
            self.env.cr.fetchall(),
            [],
            "the migration drops both columns; a nulled one still sits in every "
            "backup taken before it was nulled",
        )
