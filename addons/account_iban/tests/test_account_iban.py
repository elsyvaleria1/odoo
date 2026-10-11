from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged

from odoo.addons.account_iban.models.res_partner_bank_account import (
    check_iban,
    get_bban_from_iban,
    get_iban_part,
    normalize_iban,
    pretty_iban,
)

VALID_IBAN = "BE68539007547034"


@tagged("post_install", "-at_install")
class TestAccountIban(TransactionCase):

    def test_normalize_iban_strips_separators(self):
        self.assertEqual(normalize_iban("BE68 5390-0754_7034"), VALID_IBAN)

    def test_pretty_iban_groups_valid_in_fours(self):
        self.assertEqual(pretty_iban(VALID_IBAN), "BE68 5390 0754 7034")

    def test_pretty_iban_leaves_invalid_untouched(self):
        self.assertEqual(pretty_iban("XX"), "XX")

    def test_pretty_iban_normalizes_punctuated_input(self):
        self.assertEqual(pretty_iban("BE68 5390-0754_7034"), "BE68 5390 0754 7034")

    def test_get_bban_from_iban_drops_country_and_check(self):
        self.assertEqual(get_bban_from_iban(VALID_IBAN), "539007547034")

    def test_validate_iban_accepts_valid(self):
        self.assertIsNone(check_iban(VALID_IBAN))

    def test_validate_iban_empty_raises(self):
        with self.assertRaises(ValidationError):
            check_iban("")

    def test_validate_iban_unknown_country_raises(self):
        with self.assertRaises(ValidationError):
            check_iban("ZZ68539007547034")

    def test_validate_iban_wrong_length_raises(self):
        with self.assertRaises(ValidationError):
            check_iban("BE123")

    def test_validate_iban_bad_check_digits_raises(self):
        with self.assertRaises(ValidationError):
            check_iban("BE69539007547034")

    def test_check_iban_returns_bool(self):
        Bank = self.env["res.partner.bank.account"]
        self.assertTrue(Bank.is_valid_iban(VALID_IBAN))
        self.assertFalse(Bank.is_valid_iban("not-an-iban"))

    def test_create_does_not_mutate_caller_vals(self):
        partner = self.env["res.partner"].create({"name": "IBAN mutation probe"})
        vals = {"partner_id": partner.id, "acc_number": "BE68 5390-0754_7034"}
        original = dict(vals)
        bank = self.env["res.partner.bank.account"].create(vals)
        self.assertEqual(vals, original)
        self.assertEqual(bank.acc_number, "BE68 5390 0754 7034")

    def test_write_does_not_mutate_caller_vals(self):
        partner = self.env["res.partner"].create({"name": "IBAN mutation probe"})
        bank = self.env["res.partner.bank.account"].create(
            {"partner_id": partner.id, "acc_number": VALID_IBAN}
        )
        vals = {"acc_number": "BE68 5390-0754_7034"}
        original = dict(vals)
        bank.write(vals)
        self.assertEqual(vals, original)
        self.assertEqual(bank.acc_number, "BE68 5390 0754 7034")

    def test_get_iban_part_extracts_masked_segment(self):
        it_iban = "IT60X0542811101000000123456"
        self.assertEqual(get_iban_part(it_iban, "bank"), "05428")
        self.assertEqual(get_iban_part(it_iban, "account"), "000000123456")

    def test_get_iban_part_unrecognized_kind_returns_false(self):
        self.assertIs(get_iban_part(VALID_IBAN, "not_a_kind"), False)

    def test_get_iban_part_unmapped_country_returns_false(self):
        self.assertIs(get_iban_part("ZZ68539007547034", "bank"), False)

    def test_get_bban_returns_bban_for_iban_account(self):
        partner = self.env["res.partner"].create({"name": "IBAN mutation probe"})
        bank = self.env["res.partner.bank.account"].create(
            {"partner_id": partner.id, "acc_number": VALID_IBAN}
        )
        self.assertEqual(bank.acc_type, "iban")
        self.assertEqual(bank.get_bban(), "539007547034")

    def test_get_bban_raises_for_non_iban_account(self):
        partner = self.env["res.partner"].create({"name": "IBAN mutation probe"})
        bank = self.env["res.partner.bank.account"].create(
            {"partner_id": partner.id, "acc_number": "not-an-iban"}
        )
        self.assertNotEqual(bank.acc_type, "iban")
        with self.assertRaises(UserError):
            bank.get_bban()

    def test_get_acc_type_detects_iban(self):
        Bank = self.env["res.partner.bank.account"]
        self.assertEqual(Bank._get_acc_type(VALID_IBAN), "iban")

    def test_get_acc_type_falls_back_for_non_iban(self):
        Bank = self.env["res.partner.bank.account"]
        self.assertEqual(Bank._get_acc_type("not-an-iban"), "bank")
