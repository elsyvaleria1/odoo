from odoo.tests import common
from odoo.tools.module_data import rekey_property_values


class TestRekeyPropertyValues(common.TransactionCase):
    def test_a_relational_property_follows_its_records(self):
        spare, extra = self.env["test.unit.badge"].create(
            [{"name": "S"}, {"name": "E"}]
        )
        unit = self.env["test.unit"].create(
            {
                "name": "Unit",
                "props_definition": [
                    {"name": "spare", "type": "many2one", "comodel": "test.unit.badge"},
                    {
                        "name": "spares",
                        "type": "many2many",
                        "comodel": "test.unit.badge",
                    },
                    {"name": "count", "type": "integer"},
                ],
            }
        )
        box = self.env["test.box"].create(
            {
                "unit_id": unit.id,
                "props": {
                    "spare": spare.id,
                    "spares": [spare.id, extra.id],
                    "count": spare.id,
                },
            }
        )
        self.env.flush_all()
        rekey_property_values(
            self.env, ["test.unit.badge"], {spare.id: 900001, extra.id: 900002}
        )
        self.env.cr.execute("SELECT props FROM test_box WHERE id = %s", [box.id])
        self.assertEqual(
            self.env.cr.fetchone()[0],
            {"spare": 900001, "spares": [900001, 900002], "count": spare.id},
        )
