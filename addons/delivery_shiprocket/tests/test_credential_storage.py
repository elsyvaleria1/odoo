from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, tagged

from odoo.addons.delivery_shiprocket.models.shiprocket_request import ShipRocket


@tagged("post_install", "-at_install")
class TestShiprocketCredentials(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        product = cls.env["product.product"].create(
            {"name": "Shiprocket Delivery", "type": "service"}
        )
        cls.carrier = cls.env["delivery.carrier"].create(
            {
                "name": "Shiprocket Probe",
                "delivery_type": "shiprocket",
                "product_id": product.id,
                "shiprocket_email": "probe@example.com",
                "shiprocket_password": "a-password",
                "shiprocket_access_token": "a-token",
            }
        )

    def test_both_secrets_land_in_one_credential(self):
        self.carrier.shiprocket_password = "landed-password"
        credential = self.carrier.carrier_credential_id.sudo()

        self.assertTrue(credential)
        self.assertEqual(credential.password, "landed-password")

    def test_the_fields_read_back_what_was_written(self):
        self.carrier.write(
            {
                "shiprocket_password": "round-password",
                "shiprocket_access_token": "round-token",
            }
        )
        self.carrier.invalidate_recordset()

        self.assertEqual(self.carrier.shiprocket_password, "round-password")
        self.assertEqual(self.carrier.shiprocket_access_token, "round-token")

    def test_regenerating_the_token_leaves_the_password_alone(self):
        self.carrier.write(
            {
                "shiprocket_password": "the-password",
                "shiprocket_access_token": "first-token",
            }
        )

        self.carrier.shiprocket_access_token = "a-fresher-token"
        self.carrier.invalidate_recordset()

        self.assertEqual(self.carrier.shiprocket_access_token, "a-fresher-token")
        self.assertEqual(self.carrier.shiprocket_password, "the-password")

    def test_the_email_stays_a_plain_readable_column(self):
        field = self.env["delivery.carrier"]._fields["shiprocket_email"]

        self.assertTrue(field.store)
        self.assertFalse(field.groups)

    def test_the_two_doors_keep_their_different_visibility(self):
        user = self.env["res.users"].create(
            {
                "name": "Plain User",
                "login": "shiprocket_plain_probe",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.carrier.shiprocket_access_token = "visible-token"
        carrier = self.carrier.with_user(user)

        self.assertEqual(carrier.shiprocket_access_token, "visible-token")
        with self.assertRaises(AccessError):
            carrier.read(["shiprocket_password"])

    def test_no_plaintext_column_survives(self):
        self.env.cr.execute(
            """
            SELECT column_name FROM information_schema.columns
             WHERE table_name = 'delivery_carrier'
               AND column_name IN ('shiprocket_password', 'shiprocket_access_token')
            """
        )
        self.assertEqual(
            self.env.cr.fetchall(),
            [],
            "the migration drops both columns; a nulled one still sits in every "
            "backup taken before it was nulled",
        )

    def test_acquire_valid_token_reuses_credential(self):
        self.carrier.shiprocket_token_valid_upto = fields.Datetime.today() + timedelta(
            days=1
        )
        client = ShipRocket(self.carrier, self.carrier.log_xml)
        with patch.object(ShipRocket, "_authorize_generate_token") as authorize:
            self.assertEqual(client._acquire_access_token(), "a-token")
        authorize.assert_not_called()
        self.assertEqual(self.carrier.shiprocket_password, "a-password")

    def test_acquire_missing_or_expired_token_persists_replacement(self):
        client = ShipRocket(self.carrier, self.carrier.log_xml)
        for token in (False, "expired-token"):
            with self.subTest(token=token):
                self.carrier.write(
                    {
                        "shiprocket_access_token": token,
                        "shiprocket_token_valid_upto": fields.Datetime.today()
                        - timedelta(days=1),
                    }
                )
                with patch.object(
                    ShipRocket,
                    "_authorize_generate_token",
                    return_value={"token": "replacement"},
                ) as authorize:
                    self.assertEqual(client._acquire_access_token(), "replacement")
                authorize.assert_called_once_with()
                self.assertEqual(self.carrier.shiprocket_access_token, "replacement")
                self.assertEqual(self.carrier.shiprocket_password, "a-password")
                self.assertEqual(
                    self.carrier.shiprocket_token_valid_upto,
                    fields.Datetime.today() + timedelta(days=9),
                )

    def test_acquire_token_without_provider_token_returns_none(self):
        self.carrier.shiprocket_access_token = False
        client = ShipRocket(self.carrier, self.carrier.log_xml)
        with patch.object(ShipRocket, "_authorize_generate_token", return_value={}):
            self.assertIsNone(client._acquire_access_token())
        self.assertFalse(self.carrier.shiprocket_access_token)
        self.assertEqual(self.carrier.shiprocket_password, "a-password")
