from itertools import product

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.whatsapp.tests.common import WhatsAppCommon
from odoo.addons.whatsapp.tools import phone_validation as wa_phone_validation


@tagged("phone_validation")
class PhoneFormat(WhatsAppCommon):
    def test_phone_format(self):
        us_country = self.env.ref("base.us")
        be_country = self.env.ref("base.be")
        base_record = self.env["res.partner"].create(
            {
                "country_id": be_country.id,
                "name": "Record for Context",
            }
        )
        test_numbers = [
            "32485221100",
            "0485221100",
            "+32485221100",
            "+32 485 22 11 00",
            "0032485221100",
        ]
        expecteds = [
            "+32485221100",
            "+32 485 22 11 00",
            "32485221100",
            "+32485221100",
            "+32 485 22 11 00",
            "32485221100",
            "+32485221100",
            "+32 485 22 11 00",
            "32485221100",
            "+32485221100",
            "+32 485 22 11 00",
            "32485221100",
            "+32485221100",
            "+32 485 22 11 00",
            "32485221100",
        ]
        for (number, force_format), expected in zip(
            product(test_numbers, ("E164", "INTERNATIONAL", "WHATSAPP")),
            expecteds,
            strict=False,
        ):
            with self.subTest(number=number, force_format=force_format):
                formatted = wa_phone_validation.wa_phone_format(
                    base_record,
                    number=number,
                    force_format=force_format,
                )
                self.assertEqual(formatted, expected)

            if number == "0485221100":
                with self.assertRaises(UserError):
                    formatted = wa_phone_validation.wa_phone_format(
                        base_record,
                        number=number,
                        country=us_country,
                        force_format=force_format,
                    )
                with self.assertRaises(UserError):
                    formatted = wa_phone_validation.wa_phone_format(
                        self.env["res.partner"],
                        number=number,
                        force_format=force_format,
                    )
                continue
            with self.subTest(
                number=number, force_format=force_format, force_country=us_country
            ):
                formatted = wa_phone_validation.wa_phone_format(
                    base_record,
                    number=number,
                    country=us_country,
                    force_format=force_format,
                )
                self.assertEqual(formatted, expected)

            with self.subTest(
                number=number, force_format=force_format, force_country=False
            ):
                formatted = wa_phone_validation.wa_phone_format(
                    self.env["res.partner"],
                    number=number,
                    force_format=force_format,
                )
                self.assertEqual(formatted, expected)
