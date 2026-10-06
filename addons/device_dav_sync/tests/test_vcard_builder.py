from odoo import Command

from ..lib.vcard_builder import VCardBuilder
from odoo.addons.device.tests.common import DeviceTransactionCase


class TestVCardBuilder(DeviceTransactionCase):
    def setUp(self):
        super().setUp()

        self.builder = VCardBuilder()

        self.test_contact = self.env["res.partner"].create(
            {
                "name": "John Doe",
                "email": "john.doe@example.com",
                "phone_ids": [
                    Command.create({"number": "+1234567890", "type": "landline"})
                ],
                "street": "123 Main St",
                "city": "Anytown",
                "zip": "12345",
                "country_id": self.env.ref("base.us").id,
            }
        )

    def test_partner_to_vcard(self):
        vcard_str = self.builder.partner_to_vcard(self.test_contact, self.env)

        self.assertIn("BEGIN:VCARD", vcard_str)
        self.assertIn("END:VCARD", vcard_str)
        self.assertIn("VERSION:4.0", vcard_str)
        self.assertIn("FN:John Doe", vcard_str)
        self.assertIn("EMAIL", vcard_str)
        self.assertIn("john.doe@example.com", vcard_str)

    def test_vcard_to_partner_vals(self):
        vcard_str = """BEGIN:VCARD
VERSION:4.0
FN:Jane Smith
EMAIL:jane.smith@example.com
TEL:+1111111111
END:VCARD"""

        vals = self.builder.vcard_to_partner_vals(vcard_str, self.env)

        self.assertIn("name", vals)
        self.assertIn("email", vals)
        self.assertEqual(vals["email"], "jane.smith@example.com")

    def test_vcard_roundtrip(self):
        vcard_str = self.builder.partner_to_vcard(self.test_contact, self.env)

        vals = self.builder.vcard_to_partner_vals(vcard_str, self.env)

        self.assertIn("name", vals)
        self.assertIn("email", vals)
        self.assertEqual(vals["email"], self.test_contact.email)

    def test_vcard_with_special_characters(self):
        contact = self.env["res.partner"].create(
            {
                "name": "François Müller",
                "email": "francois@example.com",
            }
        )

        vcard_str = self.builder.partner_to_vcard(contact, self.env)

        self.assertIn("BEGIN:VCARD", vcard_str)
        self.assertIn("François", vcard_str)
