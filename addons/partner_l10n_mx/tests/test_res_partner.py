from odoo.tests.common import TransactionCase
from odoo.tools import SQL


class TestPartnerMunicipality(TransactionCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        mexico = cls.env.ref("base.mx")
        cls.state = cls.env["res.country.state"].create(
            {"name": "Test State", "code": "TST", "country_id": mexico.id}
        )
        Municipality = cls.env["l10n_mx.municipality"]
        cls.north = Municipality.create(
            {"name": "North", "code": "001", "state_id": cls.state.id}
        )
        cls.south = Municipality.create(
            {"name": "South", "code": "002", "state_id": cls.state.id}
        )
        cls.postal_code = cls.env["l10n_mx.postal_code"].create(
            {
                "code": "99951",
                "name": "Centro",
                "state_id": cls.state.id,
                "municipality_id": cls.south.id,
            }
        )

    def _municipality_of(self, partner):
        [[municipality_id]] = self.env.execute_query(
            SQL(
                "SELECT %s FROM res_partner partner WHERE partner.id = %s",
                self.env["res.partner"]._get_l10n_mx_municipality_sql(
                    SQL.identifier("partner")
                ),
                partner.id,
            )
        )
        return self.env["l10n_mx.municipality"].browse(municipality_id)

    def test_the_municipality_set_on_the_contact_wins(self) -> None:
        partner = self.env["res.partner"].create(
            {"name": "Set", "zip": "99951", "l10n_mx_municipality_id": self.north.id}
        )
        self.assertEqual(self._municipality_of(partner), self.north)

    def test_the_postal_code_picked_on_the_contact_locates_it(self) -> None:
        partner = self.env["res.partner"].create(
            {"name": "Picked", "l10n_mx_postal_code_id": self.postal_code.id}
        )
        self.assertEqual(self._municipality_of(partner), self.south)

    def test_the_zip_text_is_looked_up_in_the_catalogue(self) -> None:
        partner = self.env["res.partner"].create({"name": "Typed", "zip": " 99951 "})
        self.assertEqual(self._municipality_of(partner), self.south)

    def test_an_unknown_zip_locates_nothing(self) -> None:
        partner = self.env["res.partner"].create({"name": "Unknown", "zip": "99959"})
        self.assertFalse(self._municipality_of(partner))
