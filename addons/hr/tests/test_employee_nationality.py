from odoo.tests import tagged

from .common import TestHrCommon


@tagged("post_install", "-at_install")
class TestEmployeeNationality(TestHrCommon):
    """An employee may hold several nationalities: nationality_country_id is the
    first they hold, writing it moves a held one first, corrects the first to a
    new one or ends them all, and a rule about a country's citizens reads every
    one they hold."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mx, cls.us = cls.env.ref("base.mx"), cls.env.ref("base.us")
        cls.employee = cls.env["hr.employee"].create(
            {"name": "Dual", "nationality_country_id": cls.mx.id}
        )
        cls.employee.nationality_ids = [
            (0, 0, {"country_id": cls.us.id, "basis": "naturalization"})
        ]

    def test_the_first_nationality_is_the_primary_one(self):
        self.assertEqual(self.employee.nationality_country_id, self.mx)
        self.assertEqual(self.employee.nationality_country_ids, self.mx | self.us)
        self.assertEqual(
            self.employee.resource_id.nationality_country_ids, self.mx | self.us
        )

    def test_writing_the_primary_one_puts_it_first(self):
        self.employee.nationality_country_id = self.us
        self.assertEqual(self.employee.nationality_country_id, self.us)
        self.assertEqual(
            self.employee.nationality_ids._filter_held().country_id, self.us | self.mx
        )

    def test_a_new_primary_one_corrects_the_first(self):
        belgium = self.env.ref("base.be")
        self.employee.nationality_country_id = belgium
        self.assertEqual(self.employee.nationality_country_id, belgium)
        self.assertEqual(self.employee.nationality_country_ids, belgium | self.us)

    def test_a_lost_nationality_set_as_primary_is_held_again(self):
        held_us = self.employee.nationality_ids.filtered(
            lambda row: row.country_id == self.us
        )
        held_us.date_lost = "2020-01-01"
        self.employee.nationality_country_id = self.us
        self.assertFalse(held_us.date_lost)
        self.assertEqual(self.employee.nationality_country_ids, self.us | self.mx)

    def test_a_citizen_is_found_by_any_nationality_held(self):
        Employee = self.env["hr.employee"]
        for country in (self.mx, self.us):
            self.assertEqual(
                Employee.search(
                    [
                        ("id", "=", self.employee.id),
                        ("nationality_country_ids", "in", country.ids),
                    ]
                ),
                self.employee,
            )
        self.assertFalse(
            Employee.search(
                [
                    ("id", "=", self.employee.id),
                    ("nationality_country_ids", "not in", self.us.ids),
                ]
            )
        )

    def test_a_lost_nationality_no_longer_counts(self):
        self.employee.nationality_ids.filtered(
            lambda row: row.country_id == self.us
        ).date_lost = "2020-01-01"
        self.assertEqual(self.employee.nationality_country_ids, self.mx)
        self.assertFalse(
            self.env["hr.employee"].search(
                [
                    ("id", "=", self.employee.id),
                    ("nationality_country_ids", "in", self.us.ids),
                ]
            )
        )

    def test_a_declaration_states_the_authority_country_when_held(self):
        self.assertEqual(self.employee._get_nationality_declared_to(self.us), self.us)
        self.assertEqual(
            self.employee._get_nationality_declared_to(self.env.ref("base.be")),
            self.mx,
        )

    def test_clearing_the_primary_one_ends_the_held_nationalities(self):
        self.employee.nationality_country_id = False
        self.assertFalse(self.employee.nationality_country_ids)
        self.assertTrue(all(self.employee.nationality_ids.mapped("date_lost")))
