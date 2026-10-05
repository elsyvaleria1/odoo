from psycopg.errors import CheckViolation

from odoo.tests import common
from odoo.tools import mute_logger


class TestInheritsSharedId(common.TransactionCase):
    """A crate is its unit's row extended: it is keyed by the unit's id."""

    def test_a_new_record_takes_its_new_parent_id(self):
        crate = self.env["test.crate"].create({"name": "Crate", "label": "fragile"})
        self.assertEqual(crate.id, crate.unit_id.id)
        self.assertEqual(self.env["test.unit"].browse(crate.id).name, "Crate")

    def test_a_record_extends_an_existing_parent(self):
        unit = self.env["test.unit"].create({"name": "Loose"})
        crate = self.env["test.crate"].create({"unit_id": unit.id, "label": "boxed"})
        self.assertEqual(crate.id, unit.id)
        self.assertEqual(crate.name, "Loose")

    def test_a_batch_copied_in_takes_its_parents_ids(self):
        crates = self.env["test.crate"].create(
            [{"name": f"Crate {index}"} for index in range(60)]
        )
        self.assertEqual(crates.ids, crates.unit_id.ids)

    def test_the_parent_cannot_change(self):
        crate = self.env["test.crate"].create({"name": "Crate"})
        other = self.env["test.unit"].create({"name": "Other"})
        with (
            mute_logger("odoo.db.cursor", "odoo.sql_db"),
            self.assertRaises(CheckViolation),
            self.env.cr.savepoint(),
        ):
            crate.unit_id = other
            crate.flush_recordset()

    def test_its_references_are_its_parents(self):
        self.assertEqual(
            self.env["test.crate"]._get_reference_model_name(), "test.unit"
        )

    def test_deleting_it_deletes_its_parent(self):
        crate = self.env["test.crate"].create({"name": "Crate"})
        unit = crate.unit_id
        crate.unlink()
        self.assertFalse(unit.exists())

    def test_deleting_the_parent_deletes_it(self):
        crate = self.env["test.crate"].create({"name": "Crate"})
        crate.unit_id.unlink()
        self.assertFalse(crate.exists())

    def test_a_copy_takes_its_new_parents_id(self):
        crate = self.env["test.crate"].create({"name": "Crate", "label": "fragile"})
        copy = crate.copy()
        self.assertNotEqual(copy.id, crate.id)
        self.assertEqual(copy.id, copy.unit_id.id)
        self.assertEqual(copy.label, "fragile")
