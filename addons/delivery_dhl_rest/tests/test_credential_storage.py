"""The DHL carrier's key and secret rest in the vault; the fields are doors."""

from odoo.tests import tagged

from odoo.addons.delivery_dhl_rest.tests.test_delivery_dhl import TestDeliveryDHLCommon


@tagged("post_install", "-at_install")
class TestDhlCredentials(TestDeliveryDHLCommon):
    def setUp(self):
        super().setUp()
        self.carrier = self.delivery_carrier_dhl_be_dom

    def test_the_fixture_secrets_landed_in_one_credential(self):
        credential = self.carrier.carrier_credential_id.sudo()

        self.assertTrue(credential, "a carrier with secrets holds a credential")
        self.assertTrue(credential.api_key or credential.api_secret)

    def test_the_fields_read_back_what_was_written(self):
        self.carrier.write({"dhl_api_key": "a-key", "dhl_api_secret": "a-secret"})
        self.carrier.invalidate_recordset()

        self.assertEqual(self.carrier.dhl_api_key, "a-key")
        self.assertEqual(self.carrier.dhl_api_secret, "a-secret")

    def test_writing_one_secret_leaves_the_other_alone(self):
        # Each field has its own inverse, so they arrive one at a time. A store
        # that rewrote the whole credential would clear the sibling.
        self.carrier.write({"dhl_api_key": "first-key", "dhl_api_secret": "keep-me"})

        self.carrier.write({"dhl_api_key": "second-key"})
        self.carrier.invalidate_recordset()

        self.assertEqual(self.carrier.dhl_api_key, "second-key")
        self.assertEqual(self.carrier.dhl_api_secret, "keep-me")

    def test_a_secret_written_before_the_key_does_not_invent_one(self):
        # The first write can be either field. Satisfying the category
        # constraint with a placeholder would leave it readable as the key.
        carrier = self.env["delivery.carrier"].create(
            {
                "name": "Secret First",
                "delivery_type": "dhl_rest",
                "product_id": self.carrier.product_id.id,
            }
        )

        carrier.dhl_api_secret = "only-a-secret"

        self.assertEqual(carrier.dhl_api_secret, "only-a-secret")
        self.assertFalse(carrier.dhl_api_key, "no placeholder may read back as a key")

    def test_clearing_both_unlinks_the_credential(self):
        self.carrier.write({"dhl_api_key": "gone", "dhl_api_secret": "gone-too"})
        credential = self.carrier.carrier_credential_id

        self.carrier.write({"dhl_api_key": False, "dhl_api_secret": False})

        self.assertFalse(self.carrier.carrier_credential_id)
        self.assertFalse(credential.exists())

    def test_no_plaintext_column_survives(self):
        self.env.cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'delivery_carrier'
               AND column_name IN ('dhl_api_key', 'dhl_api_secret')
            """
        )
        self.assertEqual(
            self.env.cr.fetchall(),
            [],
            "the migration drops the columns; a nulled one still sits in every "
            "backup taken before it was nulled",
        )

    def test_a_duplicate_holds_its_own_credential_with_the_same_secrets(self):
        self.carrier.write({"dhl_api_key": "a-key", "dhl_api_secret": "a-secret"})

        duplicate = self.carrier.copy()
        duplicate.dhl_api_key = "another-key"
        (self.carrier | duplicate).invalidate_recordset()

        self.assertTrue(duplicate.carrier_credential_id)
        self.assertNotEqual(
            duplicate.carrier_credential_id, self.carrier.carrier_credential_id
        )
        self.assertEqual(duplicate.dhl_api_secret, "a-secret")
        self.assertEqual(duplicate.dhl_api_key, "another-key")
        self.assertEqual(self.carrier.dhl_api_key, "a-key")
