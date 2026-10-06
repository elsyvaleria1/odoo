# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestQualityPointOperationConstraint(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.picking_type = cls.env.ref("stock.warehouse0").manu_type_id
        product = cls.env["product.product"].create(
            {"name": "Constrained", "is_storable": True}
        )
        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "operation_ids": [
                    Command.create(
                        {
                            "name": "Assemble",
                            "workcenter_id": cls.env["mrp.workcenter"]
                            .create({"name": "WC"})
                            .id,
                        }
                    )
                ],
            }
        )

    def _vals(self, **extra):
        return {
            "title": "point",
            "picking_type_ids": [Command.set(self.picking_type.ids)],
            **extra,
        }

    def test_on_demand_is_refused_on_a_work_order_point(self):
        with self.assertRaises(ValidationError):
            self.env["quality.point"].create(
                self._vals(
                    measure_frequency_type="on_demand",
                    bom_id=self.bom.id,
                    operation_id=self.bom.operation_ids.id,
                )
            )

    def test_a_sibling_in_the_same_create_does_not_condemn_a_legal_point(self):
        """The constraint used to read `self.operation_id`, not the point's."""
        points = self.env["quality.point"].create(
            [
                self._vals(bom_id=self.bom.id, operation_id=self.bom.operation_ids.id),
                self._vals(measure_frequency_type="on_demand"),
            ]
        )
        self.assertEqual(len(points), 2)
