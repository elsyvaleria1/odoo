from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestResourceOrigin(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Resource = cls.env["resource.resource"]
        cls.mx, cls.us, cls.de = (
            cls.env.ref("base.mx"),
            cls.env.ref("base.us"),
            cls.env.ref("base.de"),
        )
        cls.press = cls.Resource.create(
            {"name": "Press", "type": "material", "tz": "UTC"}
        )
        cls.person = cls.Resource.create(
            {"name": "Ana Origin", "type": "human", "tz": "UTC"}
        )

    def test_a_thing_keeps_its_own_origin_and_its_year(self):
        self.press.write(
            {
                "date_origin": "2019-06-01",
                "origin_country_id": self.de.id,
                "place_origin": "Stuttgart",
            }
        )
        self.assertRecordValues(
            self.press,
            [
                {
                    "date_origin": date(2019, 6, 1),
                    "year_origin": 2019,
                    "origin_country_id": self.de.id,
                    "place_origin": "Stuttgart",
                }
            ],
        )

    def test_a_persons_origin_is_their_partys_private_fact(self):
        self.person.write(
            {"date_origin": "1990-04-05", "origin_country_id": self.mx.id}
        )
        facet = self.person.partner_id._get_private_facet()
        self.assertEqual(facet.parent_id, self.person.partner_id)
        self.assertEqual(facet.birthdate, date(1990, 4, 5))
        self.assertEqual(facet.country_of_birth, self.mx)
        facet.place_of_birth = "Puebla"
        self.assertEqual(self.person.place_origin, "Puebla")
        self.assertEqual(self.person.year_origin, 1990)

    def test_a_person_holds_several_nationalities(self):
        facet = self.person.partner_id._ensure_private_facet()
        self.env["resource.nationality"].create(
            [
                {"partner_id": facet.id, "country_id": self.mx.id, "basis": "birth"},
                {
                    "partner_id": facet.id,
                    "country_id": self.us.id,
                    "basis": "naturalization",
                    "date_acquired": "2015-01-01",
                },
                {
                    "partner_id": facet.id,
                    "country_id": self.de.id,
                    "basis": "descent",
                    "date_lost": "2020-01-01",
                },
            ]
        )
        self.assertEqual(self.person.nationality_country_ids, self.mx | self.us)
        self.assertEqual(
            self.Resource.search([("nationality_country_ids", "in", self.us.ids)]),
            self.person,
        )

    def test_an_imported_thing_is_nationalized(self):
        self.press.nationality_ids = [
            (0, 0, {"country_id": self.mx.id, "basis": "importation"})
        ]
        self.assertEqual(self.press.nationality_country_ids, self.mx)

    def test_a_nationality_has_one_holder_and_proof_of_its_own(self):
        with self.assertRaises(Exception), self.env.cr.savepoint():
            self.env["resource.nationality"].create({"country_id": self.mx.id})
        other = self.Resource.create({"name": "Lathe", "type": "material", "tz": "UTC"})
        other._update_identifier("serial", "SN-ORIGIN")
        with self.assertRaises(ValidationError):
            self.env["resource.nationality"].create(
                {
                    "resource_id": self.press.id,
                    "country_id": self.mx.id,
                    "identifier_id": other.identifier_ids.id,
                }
            )

    def test_a_persons_origin_is_hidden_a_things_is_not(self):
        self.person.date_origin = "1990-04-05"
        self.press.date_origin = "2019-06-01"
        user = new_test_user(self.env, login="origin_reader", groups="base.group_user")
        self.assertFalse(self.person.with_user(user).date_origin)
        self.assertEqual(self.press.with_user(user).date_origin, date(2019, 6, 1))
