"""Tests for the country-specific VAT validators and dispatch."""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestVatValidators(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]

    def test_split_vat_with_country_prefix(self):
        self.assertEqual(self.Partner._split_vat("BE0477472701"), ("BE", "0477472701"))

    def test_split_vat_without_prefix(self):
        self.assertEqual(self.Partner._split_vat("0477472701"), ("", "0477472701"))

    def test_check_vat_mx_valid_rfc(self):
        self.assertTrue(self.Partner.check_vat_mx("AAA010101AAA"))

    def test_check_vat_mx_bad_date_rejected(self):
        self.assertFalse(self.Partner.check_vat_mx("AAA011301AAA"))

    def test_check_vat_mx_bad_format_rejected(self):
        self.assertFalse(self.Partner.check_vat_mx("not-an-rfc"))

    def test_check_vat_number_dispatches_to_country(self):
        self.assertTrue(self.Partner._check_vat_number("mx", "AAA010101AAA"))
        self.assertFalse(self.Partner._check_vat_number("mx", "AAA011301AAA"))

    def test_check_vat_number_unknown_country_passes(self):
        self.assertTrue(self.Partner._check_vat_number("zz", "whatever"))


    def test_check_vat_mx_century_mapping(self):
        self.assertFalse(self.Partner.check_vat_mx("AAA990229AAA"))
        self.assertTrue(self.Partner.check_vat_mx("AAA000229AAA"))

    def test_check_vat_mx_accepts_moral_and_separated_forms(self):
        self.assertTrue(self.Partner.check_vat_mx("ABCD010101AAA"))
        self.assertTrue(self.Partner.check_vat_mx("AÑA010101AAA"))
        self.assertTrue(self.Partner.check_vat_mx("AAA-010101-AAA"))

    def test_check_vat_mx_rejects_malformed(self):
        self.assertFalse(self.Partner.check_vat_mx("AA010101AAA"))
        self.assertFalse(self.Partner.check_vat_mx("AAA010101AAAX"))

    def test_check_vat_ch_mod11_checksum(self):
        self.assertTrue(self.Partner.check_vat_ch("E123456788MWST"))
        self.assertTrue(self.Partner.check_vat_ch("E-123.456.788 TVA"))
        self.assertFalse(self.Partner.check_vat_ch("E123456789MWST"))

    def test_check_vat_ch_rejects_english_abbreviation(self):
        self.assertFalse(self.Partner.check_vat_ch("E123456788VAT"))

    def test_check_vat_gr_allows_edi_test_numbers(self):
        self.assertTrue(self.Partner.check_vat_gr("047747270"))
        self.assertFalse(self.Partner.check_vat_gr("12345"))

    def test_check_vat_gt_allows_edi_test_numbers(self):
        self.assertTrue(self.Partner.check_vat_gt("11201220K"))
        self.assertTrue(self.Partner.check_vat_gt("981234567890K"))
        self.assertFalse(self.Partner.check_vat_gt("123"))

    def test_check_vat_ro_natural_person_tins(self):
        self.assertTrue(self.Partner.check_vat_ro("1900101123456"))
        self.assertTrue(self.Partner.check_vat_ro("9000123456789"))
        self.assertFalse(self.Partner.check_vat_ro("1901301123456"))

    def test_check_vat_hu_tin_formats(self):
        self.assertTrue(self.Partner.check_vat_hu("12345678-1-23"))
        self.assertTrue(self.Partner.check_vat_hu("8123456789"))
        self.assertTrue(self.Partner.check_vat_hu("12345678"))
        self.assertFalse(self.Partner.check_vat_hu("7123456789"))

    def test_check_vat_ec_ruc_length_and_cleaning(self):
        self.assertTrue(self.Partner.check_vat_ec("1234567890"))
        self.assertTrue(self.Partner.check_vat_ec("1234567890123"))
        self.assertTrue(self.Partner.check_vat_ec("123-456.789 0"))
        self.assertFalse(self.Partner.check_vat_ec("123456789"))

    def test_check_vat_jp_strips_the_t_prefix(self):
        self.assertTrue(self.Partner.check_vat_jp("1000000000008"))
        self.assertTrue(self.Partner.check_vat_jp("T1000000000008"))
        self.assertFalse(self.Partner.check_vat_jp("T1000000000009"))

    def test_check_vat_al_requires_ten_characters(self):
        self.assertTrue(self.Partner.check_vat_al("K12345678L"))
        self.assertFalse(self.Partner.check_vat_al("K1234567L"))
