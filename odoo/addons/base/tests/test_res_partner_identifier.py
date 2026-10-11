from unittest.mock import patch

from psycopg.errors import UniqueViolation

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestPartnerIdentifier(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Type = cls.env["res.partner.identifier.type"]
        cls.Identifier = cls.env["res.partner.identifier"]
        cls.Partner = cls.env["res.partner"]
        cls.mexico = cls.env.ref("base.mx")
        cls.rfc = cls.Type.create(
            {
                "name": "Kernel Test RFC",
                "code": "TEST_RFC",
                "country_ids": [(6, 0, cls.mexico.ids)],
                "pattern": r"[A-Z&Ñ]{3,4}[0-9]{6}[A-Z0-9]{3}",
            }
        )
        cls.curp = cls.Type.create(
            {
                "name": "Kernel Test CURP",
                "code": "TEST_CURP",
                "pattern": r"[A-Z]{4}[0-9]{6}[HM][A-Z]{5}[A-Z0-9]{2}",
            }
        )
        cls.company = cls.Partner.create(
            {
                "name": "Vantage SA de CV",
                "is_company": True,
                "country_id": cls.mexico.id,
            }
        )

    def _identify(self, partner, code, value):
        return partner.env["res.partner.identifier"].create(
            {
                "partner_id": partner.id,
                "type_id": self.Type.search([("code", "=", code)]).id,
                "value": value,
            }
        )

    def test_punctuation_and_case_do_not_change_the_identifier(self):
        self._identify(self.company, "TEST_RFC", "van-850101-qw1")

        identifier = self.company.identifier_ids
        self.assertEqual(identifier.value, "van-850101-qw1")
        self.assertEqual(identifier.normalized_value, "VAN850101QW1")

    def test_a_value_another_contact_holds_is_refused(self):
        self._identify(self.company, "TEST_RFC", "VAN-850101-QW1")
        impostor = self.Partner.create({"name": "Impostor SA", "is_company": True})

        with self.assertRaises(ValidationError):
            with self.cr.savepoint():
                self._identify(impostor, "TEST_RFC", "van850101qw1")

    def test_a_contacts_own_address_may_share_its_identifier(self):
        self._identify(self.company, "TEST_RFC", "VAN850101QW1")
        address = self.Partner.create(
            {
                "name": "Vantage Warehouse",
                "parent_id": self.company.id,
                "type": "delivery",
            }
        )

        self._identify(address, "TEST_RFC", "VAN850101QW1")

        self.assertEqual(address.identifier_ids.value, "VAN850101QW1")

    def test_a_malformed_value_is_refused_by_the_types_own_format(self):
        with self.assertRaises(ValidationError):
            with self.cr.savepoint():
                self._identify(self.company, "TEST_CURP", "not-a-curp")

    def test_one_value_per_type_unless_the_type_allows_several(self):
        self._identify(self.company, "TEST_RFC", "VAN850101QW1")

        with self.assertRaises(ValidationError):
            with self.cr.savepoint():
                self.Identifier.create(
                    {
                        "partner_id": self.company.id,
                        "type_id": self.rfc.id,
                        "value": "ABC850101XY9",
                    }
                )

        self.rfc.multiple_per_contact = True
        second = self.Identifier.create(
            {
                "partner_id": self.company.id,
                "type_id": self.rfc.id,
                "value": "ABC850101XY9",
            }
        )
        self.assertIn(second, self.company.identifier_ids)

    def test_a_collision_inside_one_batch_is_caught(self):
        rival = self.Partner.create({"name": "Rival SA", "is_company": True})

        with self.assertRaises(ValidationError):
            with self.cr.savepoint():
                self.Identifier.create(
                    [
                        {
                            "partner_id": self.company.id,
                            "type_id": self.rfc.id,
                            "value": "VAN850101QW1",
                        },
                        {
                            "partner_id": rival.id,
                            "type_id": self.rfc.id,
                            "value": "van-850101-qw1",
                        },
                    ]
                )

    def test_unrelated_identifiers_in_one_batch_are_all_accepted(self):
        rival = self.Partner.create({"name": "Rival SA", "is_company": True})

        created = self.Identifier.create(
            [
                {
                    "partner_id": self.company.id,
                    "type_id": self.rfc.id,
                    "value": "VAN850101QW1",
                },
                {
                    "partner_id": rival.id,
                    "type_id": self.rfc.id,
                    "value": "RIV850101ZZ9",
                },
            ]
        )

        self.assertEqual(len(created), 2)

    def test_two_types_cannot_share_a_code(self):
        with self.assertRaises(UniqueViolation):
            with self.cr.savepoint():
                self.Type.create({"name": "Kernel Test RFC Twin", "code": "TEST_RFC"})

    def test_a_format_that_is_not_a_regular_expression_is_refused(self):
        with self.assertRaises(ValidationError):
            with self.cr.savepoint():
                self.Type.create(
                    {"name": "Broken", "code": "TEST_BROKEN", "pattern": "([A-Z"}
                )

    def test_a_code_specific_rule_runs_after_the_format(self):
        checked = []

        def check_test_rfc(value):
            checked.append(value)
            return value.startswith("VAN")

        with patch.object(
            type(self.rfc),
            "_get_code_checkers",
            lambda self: {"test_rfc": check_test_rfc},
        ):
            self._identify(self.company, "TEST_RFC", "VAN850101QW1")
            self.assertEqual(checked, ["VAN850101QW1"])

            with self.assertRaises(ValidationError):
                with self.cr.savepoint():
                    self._identify(self.company, "TEST_RFC", "ZZZ850101QW1")

    def test_a_value_with_non_ascii_letters_is_normalized_not_stripped(self):
        self._identify(self.company, "TEST_RFC", "ÑAM-010101-AB1")
        identifier = self.company.identifier_ids.filtered(
            lambda i: i.type_id == self.rfc
        )
        self.assertEqual(identifier.value, "ÑAM-010101-AB1")
        self.assertEqual(identifier.normalized_value, "ÑAM010101AB1")

        amp = self.Partner.create({"name": "A&B SA", "is_company": True})
        self._identify(amp, "TEST_RFC", "A&B-010101-AB1")
        self.assertEqual(
            amp.identifier_ids.filtered(
                lambda i: i.type_id == self.rfc
            ).normalized_value,
            "A&B010101AB1",
        )

    def test_a_clash_with_an_unreadable_holder_raises_validation_not_access(self):
        company_b = self.env["res.company"].create({"name": "Other Co"})
        hidden = self.Partner.create(
            {"name": "Hidden Holder", "company_id": company_b.id}
        )
        self.Identifier.create(
            {
                "partner_id": hidden.id,
                "type_id": self.rfc.id,
                "value": "VAN850101QW1",
            }
        )
        manager = self.env["res.users"].create(
            {
                "name": "Partner Manager A",
                "login": "identifier_pm_a",
                "company_ids": [(6, 0, self.env.ref("base.main_company").ids)],
                "company_id": self.env.ref("base.main_company").id,
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("base.group_partner_manager").id,
                        ],
                    )
                ],
            }
        )
        mine = self.Partner.create({"name": "Mine A"})
        with self.assertRaises(ValidationError):
            with self.cr.savepoint():
                self._identify(mine.with_user(manager), "TEST_RFC", "VAN850101QW1")

    def test_a_code_does_not_collide_with_a_model_method(self):
        for code in ("hook", "pattern_compiles"):
            with self.subTest(code=code):
                self.Type.create(
                    {
                        "name": f"Collide {code}",
                        "code": code,
                        "pattern": r"[A-Z]{3}[0-9]{3}",
                    }
                )
                partner = self.Partner.create(
                    {"name": f"Collide {code} Co", "is_company": True}
                )
                self._identify(partner, code, "ABC123")
                self.assertEqual(partner.identifier_ids.value, "ABC123")
