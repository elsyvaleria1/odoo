from psycopg import IntegrityError

from odoo.tests import BaseCase, TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.delivery.usps import prepare_usps_phone_number, split_zip_plus_four


@tagged("post_install", "-at_install")
class TestDeliveryZipPrefix(TransactionCase):
    def test_create_without_name_raises_cleanly(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.db.cursor"):
            self.env["delivery.zip.prefix"].create({})

    def test_create_uppercases_name(self):
        prefix = self.env["delivery.zip.prefix"].create({"name": "abc"})
        self.assertEqual(prefix.name, "ABC")


class TestUspsWireValues(BaseCase):
    def test_phone_payload_digits_and_extension(self):
        for phone, expected in (
            ("8005551212", "8005551212"),
            ("+1 (800) 555-1212 ext. 42", "800555121242"),
            ("800.555.1212", "8005551212"),
            ("8005551212 extension", "8005551212"),
            ("8005551212\n", "8005551212"),
        ):
            with self.subTest(phone=phone):
                self.assertEqual(prepare_usps_phone_number(phone), expected)

    def test_invalid_phone_returns_false(self):
        for phone in ("", "123", "800555121"):
            with self.subTest(phone=phone):
                self.assertIs(prepare_usps_phone_number(phone), False)

    def test_phone_requires_text(self):
        for phone in (None, False, 8005551212):
            with self.subTest(phone=phone), self.assertRaises(TypeError):
                prepare_usps_phone_number(phone)

    def test_zip_parts_preserve_unrecognized_input(self):
        for zipcode, expected in (
            ("12345", ["12345", ""]),
            ("12345-6789", ["12345", "6789"]),
            ("12345-6789\n", ["12345", "6789\n"]),
            ("invalid-zip", ["invalid-zip", ""]),
            ("", ["", ""]),
        ):
            with self.subTest(zipcode=zipcode):
                self.assertEqual(split_zip_plus_four(zipcode), expected)
        self.assertIsNot(split_zip_plus_four("12345"), split_zip_plus_four("12345"))

    def test_zip_requires_text(self):
        for zipcode in (None, False, 12345):
            with self.subTest(zipcode=zipcode), self.assertRaises(TypeError):
                split_zip_plus_four(zipcode)
