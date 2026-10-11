"""Tests for the GS1 date decoding helper."""

import datetime

from freezegun import freeze_time

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestGs1Date(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.nomenclature = cls.env["barcode.nomenclature"].create(
            {"name": "GS1 date test nomenclature", "is_gs1_nomenclature": True}
        )

    def test_full_date_decoded(self):
        self.assertEqual(
            self.nomenclature.gs1_date_to_date("260115"), datetime.date(2026, 1, 15)
        )

    def test_zero_day_uses_month_end(self):
        self.assertEqual(
            self.nomenclature.gs1_date_to_date("260200"), datetime.date(2026, 2, 28)
        )

    @freeze_time("2026-06-15")
    def test_century_rollover_for_far_future(self):
        self.assertEqual(
            self.nomenclature.gs1_date_to_date("991231"), datetime.date(1999, 12, 31)
        )

    def test_invalid_date_raises(self):
        with self.assertRaises(ValidationError):
            self.nomenclature.gs1_date_to_date("260230")
