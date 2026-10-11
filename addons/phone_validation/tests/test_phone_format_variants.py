from odoo.tests import TransactionCase, tagged

from odoo.addons.phone_validation.tools.phone_validation import (
    phone_format,
    phone_get_country_code_for_number,
)


@tagged("post_install", "-at_install")
class TestPhoneFormatVariants(TransactionCase):

    BE_LOCAL = "0485112233"
    FR_NUMBER = "+33485112233"

    def test_a_local_number_can_be_written_the_way_it_is_dialled(self):
        self.assertEqual(
            phone_format(self.BE_LOCAL, "BE", 32, force_format="NATIONAL"),
            "0485 11 22 33",
        )

    def test_a_foreign_number_is_never_written_as_a_local_one(self):
        self.assertEqual(
            phone_format(self.FR_NUMBER, "BE", 32, force_format="NATIONAL"),
            "+33 4 85 11 22 33",
        )

    def test_a_number_can_be_written_as_a_dialling_link(self):
        self.assertEqual(
            phone_format(self.BE_LOCAL, "BE", 32, force_format="RFC3966"),
            "tel:+32-485-11-22-33",
        )

    def test_the_country_of_a_number_is_read_from_the_number_itself(self):
        self.assertEqual(phone_get_country_code_for_number(self.FR_NUMBER), "FR")

    def test_a_number_that_names_no_country_reports_none(self):
        self.assertEqual(phone_get_country_code_for_number("abc"), "")
