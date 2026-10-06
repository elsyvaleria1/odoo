from odoo.addons.quality_control.tests.test_common import TestQualityCommon


class TestQualityMrpCommon(TestQualityCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("base.group_user").write(
            {"implied_ids": [(4, cls.env.ref("stock.group_production_lot").id)]}
        )

        cls.product_uom_id = cls.env.ref("uom.product_uom_unit").id
        cls.product = cls.env["product.product"].create(
            {
                "name": "Drawer",
                "is_storable": True,
                "uom_id": cls.product_uom_id,
                "tracking": "lot",
            }
        )
        cls.product_id = cls.product.id
        cls.product_tmpl_id = cls.product.product_tmpl_id.id
        cls.picking_type_id = cls.env.ref("stock.warehouse0").manu_type_id.id

        cls.product_product_drawer_drawer = cls.env["product.product"].create(
            {"name": "Drawer Black", "is_storable": True, "tracking": "lot"}
        )
        product_product_drawer_case = cls.env["product.product"].create(
            {"name": "Drawer Case Black", "is_storable": True, "tracking": "lot"}
        )
        cls.bom = cls.env["mrp.bom"].create(
            {
                "product_tmpl_id": cls.product_tmpl_id,
                "product_uom_id": cls.product_uom_id,
                "bom_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": cls.product_product_drawer_drawer.id,
                            "product_qty": 1,
                            "product_uom_id": cls.product_uom_id,
                            "sequence": 1,
                        },
                    ),
                    (
                        0,
                        0,
                        {
                            "product_id": product_product_drawer_case.id,
                            "product_qty": 1,
                            "product_uom_id": cls.product_uom_id,
                            "sequence": 1,
                        },
                    ),
                ],
            }
        )
        cls.bom_id = cls.bom.id

        cls.lot_product_27_0 = cls.env["product.trace"].create(
            {
                "name": "0000000000030",
                "product_id": cls.product_id,
            }
        )
        cls.lot_product_product_drawer_drawer_0 = cls.env["product.trace"].create(
            {
                "name": "0000000010001",
                "product_id": cls.product_product_drawer_drawer.id,
            }
        )
        cls.lot_product_product_drawer_case_0 = cls.env["product.trace"].create(
            {
                "name": "0000000020045",
                "product_id": product_product_drawer_case.id,
            }
        )

        # Both components track inventory, so a manufacturing order reserves them
        # rather than inventing a line per component. Without stock there is no
        # move line for a quality check to hang off, and the Form that edits one
        # indexes into an empty list.
        warehouse = cls.env.ref("stock.warehouse0")
        cls.env["stock.quant"].with_context(inventory_mode=True).create(
            [
                {
                    "product_id": lot.product_id.id,
                    "location_id": warehouse.lot_stock_id.id,
                    "trace_id": lot.id,
                    "inventory_quantity": 100,
                }
                for lot in (
                    cls.lot_product_product_drawer_drawer_0,
                    cls.lot_product_product_drawer_case_0,
                )
            ]
        )._apply_inventory()
