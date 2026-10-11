from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import BaseCase

from odoo.addons.phone_validation.tools import phone_validation


@tagged("phone_validation")
class TestPhonenumbers(BaseCase):
    def test_country_code_falsy(self):
        self.assertEqual(
            phone_validation.phone_format(
                "0456998877", "BE", "32", force_format="E164"
            ),
            "+32456998877",
        )
        with self.assertRaises(UserError):
            self.assertEqual(
                phone_validation.phone_format(
                    "0456998877", None, "32", force_format="E164"
                ),
                "+32456998877",
            )

    def test_get_region_data_for_number(self):
        for source, (exp_code, exp_national_number, exp_phone_code) in zip(
            [
                "+32456998877",
                "+1-613-555-0177",
                "+1-202-555-0124",
            ],
            [
                ("BE", "456998877", "32"),
                ("CA", "6135550177", "1"),
                ("US", "2025550124", "1"),
            ],
            strict=True,
        ):
            with self.subTest(source=source):
                self.assertDictEqual(
                    phone_validation.phone_get_region_data_for_number(source),
                    {
                        "code": exp_code,
                        "national_number": exp_national_number,
                        "phone_code": exp_phone_code,
                    },
                )

    def test_phone_format_error(self):
        with self.assertRaises(UserError):
            phone_validation.phone_format("abc", "BE", "32")

    def test_phone_format_e164_brazil(self):
        for number, expected_number in [
            ("11 6123 4560", "+5511961234560"),
            ("+55 11 6123 4561", "+5511961234561"),
            ("11 2345 6789", "+551123456789"),
            ("+55 11 2345 6798", "+551123456798"),
        ]:
            res = phone_validation.phone_format(number, "BR", "55", force_format="E164")
            self.assertEqual(res, expected_number)

    def test_phone_format_e164_mexico(self):
        for number, expected_number in [
            ("+5215585440659", "+525585440659"),
            ("15585440749", "+525585440749"),
            ("+525595440749", "+525595440749"),
            ("5585460749", "+525585460749"),
        ]:
            with self.subTest(number=number, expected_number=expected_number):
                res = phone_validation.phone_format(
                    number, "MX", "52", force_format="E164"
                )
                self.assertEqual(res, expected_number)
