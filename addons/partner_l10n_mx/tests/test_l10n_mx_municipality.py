from psycopg import IntegrityError

from odoo.tests.common import TransactionCase


class MunicipalityTestBase(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.Municipality = cls.env["l10n_mx.municipality"]
        cls.mexico = cls.env.ref("base.mx")
        # An own state: a database with the real municipalities loaded already
        # holds codes 001, 002... in every real state.
        cls.state = cls.env["res.country.state"].create(
            {
                "name": "Test State",
                "code": "TST",
                "country_id": cls.mexico.id,
            }
        )


class TestMunicipalityBasic(MunicipalityTestBase):
    def test_create_municipality(self) -> None:
        municipality = self.Municipality.create(
            {
                "name": "Guadalajara",
                "code": "039",
                "state_id": self.state.id,
            }
        )

        self.assertEqual(municipality.name, "Guadalajara")
        self.assertEqual(municipality.code, "039")
        self.assertEqual(municipality.state_id, self.state)

    def test_municipality_partner_count_initial(self) -> None:
        municipality = self.Municipality.create(
            {
                "name": "Test Municipality",
                "code": "001",
                "state_id": self.state.id,
            }
        )

        self.assertEqual(municipality.partner_count, 0)


class TestMunicipalityDisplayName(MunicipalityTestBase):
    def test_display_name_format(self) -> None:
        municipality = self.Municipality.create(
            {
                "name": "Monterrey",
                "code": "002",
                "state_id": self.state.id,
            }
        )

        self.assertIn("Monterrey", municipality.display_name)
        self.assertIn(self.state.name, municipality.display_name)
        self.assertIn(",", municipality.display_name)


class TestMunicipalityConstraints(MunicipalityTestBase):
    def test_unique_code_per_state(self) -> None:
        self.Municipality.create(
            {
                "name": "First Municipality",
                "code": "UNQ",
                "state_id": self.state.id,
            }
        )

        with self.assertRaises(IntegrityError):
            self.Municipality.create(
                {
                    "name": "Second Municipality",
                    "code": "UNQ",
                    "state_id": self.state.id,
                }
            )


class TestMunicipalityActions(MunicipalityTestBase):
    def test_action_view_partners(self) -> None:
        municipality = self.Municipality.create(
            {
                "name": "Action Test",
                "code": "ACT",
                "state_id": self.state.id,
            }
        )

        action = municipality.action_view_partners()

        self.assertEqual(action["type"], "ir.actions.act_window")
        self.assertEqual(action["res_model"], "res.partner")
        self.assertIn(
            ("l10n_mx_municipality_id", "=", municipality.id), action["domain"]
        )
