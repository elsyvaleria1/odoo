from psycopg import IntegrityError

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger


@tagged("post_install", "-at_install")
class TestResourceIdentity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Resource = cls.env["resource.resource"]
        cls.serial = cls.env.ref("base.identifier_type_serial")
        cls.grid = cls.Resource.create(
            {"name": "Grid Supply", "type": "intangible", "tz": "UTC"}
        )
        cls.press = cls.Resource.create(
            {"name": "Press", "type": "material", "tz": "UTC"}
        )

    def test_a_resource_carries_its_identifiers(self):
        self.press._update_identifier("serial", "SN-0001")
        self.assertEqual(self.press._get_identifier("serial"), "SN-0001")
        self.press._update_identifier("serial", "SN-0002")
        self.assertEqual(len(self.press.identifier_ids), 1)
        self.assertEqual(self.press._get_identifier("serial"), "SN-0002")
        self.press._update_identifier("serial", False)
        self.assertFalse(self.press.identifier_ids)
        self.assertIsNone(self.press._get_identifier("serial"))

    def test_a_resource_is_found_by_the_absence_of_an_identifier(self):
        self.press._update_identifier("serial", "SN-0001")
        both = self.press | self.grid
        scope = [("id", "in", both.ids)]

        def found(condition):
            return self.Resource.search([condition, *scope])

        self.assertEqual(found(("serial_number", "=", False)), self.grid)
        self.assertEqual(found(("serial_number", "!=", False)), self.press)
        self.assertEqual(found(("serial_number", "in", ["SN-0001", False])), both)
        self.assertEqual(
            found(("serial_number", "not in", ["SN-0001", False])),
            self.Resource,
        )
        self.assertEqual(found(("serial_number", "=", "SN-0001")), self.press)
        self.assertEqual(found(("serial_number", "!=", "SN-0001")), self.grid)
        self.assertEqual(found(("serial_number", "ilike", "sn-")), self.press)
        self.assertEqual(found(("serial_number", "not ilike", "sn-")), self.grid)

    def test_an_identifier_names_one_resource(self):
        self.press._update_identifier("serial", "SN-0001")
        with self.assertRaises(ValidationError):
            self.grid._update_identifier("serial", "sn 0001")

    def test_an_intangible_resource_is_metered(self):
        meter = self.env["resource.meter"].create(
            {"resource_id": self.grid.id, "name": "Supply", "kind": "hours"}
        )
        meter.record(10)
        meter.record(25)
        self.assertEqual(self.grid.meter_ids, meter)
        self.assertEqual(meter.value, 25)
        with self.assertRaises(ValidationError):
            meter.record(5)

    def test_a_resource_is_not_disposed_of_before_it_is_acquired(self):
        self.press.date_acquisition = "2026-03-01"
        with (
            self.assertRaises(IntegrityError),
            mute_logger("odoo.sql_db", "odoo.db.cursor"),
            self.env.cr.savepoint(),
        ):
            self.press.date_disposal = "2026-02-01"
            self.env.flush_all()

    def test_a_resource_values_in_its_companys_currency(self):
        self.assertEqual(self.press.currency_id, self.press.company_id.currency_id)
