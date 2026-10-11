"""The bpost passphrase rests in the vault; the field is a door (ADR-0081).

These are the module's first STANDARD tests: `test_delivery_bpost.py` is
`@tagged('-standard', 'external')` and talks to the real bpost API, so it does
not run in a normal suite and guards nothing here.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestBpostCredentials(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        product = cls.env["product.product"].create(
            {"name": "bpost Delivery", "type": "service"}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "bpost Probe",
                "delivery_type": "bpost",
                "product_id": product.id,
                "bpost_account_number": "123456",
                "bpost_developer_password": "a-passphrase",
            }
        )

    def test_the_passphrase_lands_in_the_vaults_password_field(self):
        credential = self.carrier.carrier_credential_id.sudo()

        self.assertTrue(credential)
        self.assertEqual(credential.password, "a-passphrase")

    def test_the_field_reads_back_what_was_written(self):
        self.carrier.bpost_developer_password = "round-trip"
        self.carrier.invalidate_recordset()

        self.assertEqual(self.carrier.bpost_developer_password, "round-trip")

    def test_the_account_number_stays_a_plain_column(self):
        field = self.env["delivery.carrier"]._fields["bpost_account_number"]

        self.assertTrue(field.store)
        self.assertFalse(field.compute)
        self.assertEqual(self.carrier.bpost_account_number, "123456")

    def test_clearing_the_passphrase_unlinks_the_credential(self):
        credential = self.carrier.carrier_credential_id
        self.assertTrue(credential)

        self.carrier.bpost_developer_password = False

        self.assertFalse(self.carrier.carrier_credential_id)
        self.assertFalse(credential.exists())

    def test_no_plaintext_column_survives(self):
        self.env.cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'delivery_carrier'
               AND column_name = 'bpost_developer_password'
            """
        )
        self.assertEqual(
            self.env.cr.fetchall(),
            [],
            "the migration drops the column; a nulled one still sits in every "
            "backup taken before it was nulled",
        )
