import base64
import logging

from odoo import Command, fields, http
from odoo.tests import patch, tagged
from odoo.tools.misc import file_open

from odoo.addons.stock_barcode.controllers.stock_barcode import StockBarcodeController
from odoo.addons.stock_barcode.tests.test_barcode_client_action import (
    TestBarcodeClientAction,
)

_logger = logging.getLogger(__name__)


@tagged("post_install", "-at_install")
class TestInventoryAdjustmentBarcodeClientAction(TestBarcodeClientAction):
    def create_serial_numbers(self, product, start_index, quantity=1, prefix="sn"):
        return self.env["product.trace"].create(
            [
                {
                    "name": f"{prefix}{start_index + n}",
                    "product_id": product.id,
                    "company_id": self.env.company.id,
                }
                for n in range(quantity)
            ]
        )

    def test_inventory_adjustment(self):
        self.start_tour(
            "/odoo/barcode", "test_inventory_adjustment", login="admin", timeout=180
        )

        inventory_moves = self.env["stock.move"].search(
            [
                ("product_id", "in", [self.product1.id, self.product2.id]),
                ("is_inventory", "=", True),
            ]
        )
        self.assertEqual(len(inventory_moves), 2)
        self.assertEqual(inventory_moves.mapped("quantity"), [2.0, 2.0])
        self.assertEqual(inventory_moves.mapped("state"), ["done", "done"])

        quants = self.env["stock.quant"].search(
            [
                ("product_id", "in", [self.product1.id, self.product2.id]),
                ("location_id.usage", "=", "internal"),
            ]
        )
        self.assertEqual(quants.mapped("quantity"), [2.0, 2.0])
        self.assertEqual(quants.mapped("inventory_quantity"), [0, 0])
        self.assertEqual(quants.mapped("inventory_diff_quantity"), [0, 0])

    def test_inventory_adjustment_dont_update_location(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 5
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf2, 5
        )
        quants = self.env["stock.quant"].search([("product_id", "=", self.product1.id)])
        quants.user_id = self.env.user
        quants.inventory_quantity_set = True
        quants.inventory_date = fields.Date.today()

        self.start_tour(
            "/odoo/barcode",
            "test_inventory_adjustment_dont_update_location",
            login="admin",
            timeout=180,
        )
        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product1.id),
                ("location_id.usage", "=", "internal"),
            ]
        )
        self.assertRecordValues(
            quants,
            [
                {"location_id": self.stock_location.id, "quantity": 1},
                {"location_id": self.shelf2.id, "quantity": 0},
                {"location_id": self.shelf1.id, "quantity": 1},
            ],
        )

    def test_inventory_adjustment_multi_company(self):
        company_a = self.env["res.company"].create({"name": "Comp A - F2 FTW"})
        company_b = self.env["res.company"].create({"name": "Comp B - F3 Wee-Wee Pool"})
        self.env.user.write(
            {
                "company_ids": [Command.link(company_a.id), Command.link(company_b.id)],
                "company_id": company_a.id,
            }
        )
        self.product1.company_id = company_a
        self.product2.company_id = company_b
        product_no_company = self.env["product.product"].create(
            {
                "name": "Company-less Product",
                "is_storable": True,
                "barcode": "product_no_company",
            }
        )
        company_a_location = self.env["stock.location"].search(
            [("company_id", "=", company_a.id), ("usage", "=", "internal")], limit=1
        )
        self.env["stock.quant"]._update_available_quantity(
            product_no_company, company_a_location, 2
        )
        wizard_request_count = self.env["wizard.stock.quant.request.count"].create(
            {
                "user_id": self.env.user.id,
                "quant_ids": product_no_company.stock_quant_ids.ids,
                "show_expected_quantity": True,
            }
        )
        wizard_request_count.action_request_count()
        self.start_tour(
            "/odoo",
            "test_inventory_adjustment_multi_company",
            login="admin",
            timeout=180,
        )
        inventory_moves = self.env["stock.move"].search(
            [
                ("is_inventory", "=", True),
                (
                    "product_id",
                    "in",
                    (self.product1 | self.product2 | product_no_company).ids,
                ),
            ]
        )
        self.assertRecordValues(
            inventory_moves.sorted(lambda mv: (mv.product_id.id, mv.id)),
            [
                {
                    "product_id": self.product1.id,
                    "quantity": 1,
                    "company_id": company_a.id,
                },
                {
                    "product_id": self.product2.id,
                    "quantity": 1,
                    "company_id": company_b.id,
                },
                {
                    "product_id": product_no_company.id,
                    "quantity": 1,
                    "company_id": company_a.id,
                },
                {
                    "product_id": product_no_company.id,
                    "quantity": 1,
                    "company_id": company_b.id,
                },
            ],
        )

    def test_inventory_adjustment_multi_location(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        self.start_tour(
            "/odoo/barcode",
            "test_inventory_adjustment_multi_location",
            login="admin",
            timeout=180,
        )

        inventory_moves = self.env["stock.move"].search(
            [
                ("product_id", "in", [self.product1.id, self.product2.id]),
                ("is_inventory", "=", True),
            ]
        )
        self.assertEqual(len(inventory_moves), 4)
        self.assertEqual(
            inventory_moves.mapped("state"), ["done", "done", "done", "done"]
        )
        inventory_move_in_WH_stock = inventory_moves.filtered(
            lambda l: l.location_dest_id == self.stock_location
        )
        self.assertEqual(
            set(inventory_move_in_WH_stock.mapped("product_id")),
            {self.product1, self.product2},
        )
        self.assertEqual(
            inventory_move_in_WH_stock.filtered(
                lambda l: l.product_id == self.product1
            ).quantity,
            2.0,
        )
        self.assertEqual(
            inventory_move_in_WH_stock.filtered(
                lambda l: l.product_id == self.product2
            ).quantity,
            1.0,
        )

        inventory_move_in_shelf1 = inventory_moves.filtered(
            lambda l: l.location_dest_id == self.shelf1
        )
        self.assertEqual(len(inventory_move_in_shelf1), 1)
        self.assertEqual(inventory_move_in_shelf1.product_id, self.product2)
        self.assertEqual(inventory_move_in_shelf1.quantity, 1.0)

        inventory_move_in_shelf2 = inventory_moves.filtered(
            lambda l: l.location_dest_id == self.shelf2
        )
        self.assertEqual(len(inventory_move_in_shelf2), 1)
        self.assertEqual(inventory_move_in_shelf2.product_id, self.product1)
        self.assertEqual(inventory_move_in_shelf2.quantity, 1.0)

    def test_inventory_adjustment_tracked_product(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )
        self.start_tour(
            "/odoo/barcode",
            "test_inventory_adjustment_tracked_product",
            login="admin",
            timeout=180,
        )

        inventory_moves = self.env["stock.move"].search(
            [
                ("product_id", "in", [self.productlot1.id, self.productserial1.id]),
                ("is_inventory", "=", True),
            ]
        )
        self.assertEqual(len(inventory_moves), 7)
        self.assertTrue(all(s == "done" for s in inventory_moves.mapped("state")))

        moves_with_lot = inventory_moves.filtered(
            lambda l: l.product_id == self.productlot1
        )
        moves_with_sn = inventory_moves.filtered(
            lambda l: l.product_id == self.productserial1
        )
        mls_with_lot = moves_with_lot.move_line_ids
        mls_with_sn = moves_with_sn.move_line_ids
        self.assertEqual(len(mls_with_lot), 3)
        self.assertEqual(len(mls_with_sn), 4)
        self.assertEqual(mls_with_lot.mapped("trace_id.name"), ["lot1", "lot2", "lot3"])
        self.assertEqual(
            mls_with_lot.filtered(lambda ml: ml.trace_id.name == "lot1").qty_done, 3
        )
        self.assertEqual(
            mls_with_lot.filtered(lambda ml: ml.trace_id.name == "lot2").qty_done, 1
        )
        self.assertEqual(
            mls_with_lot.filtered(lambda ml: ml.trace_id.name == "lot3").qty_done, 1
        )
        self.assertEqual(
            set(mls_with_sn.mapped("trace_id.name")), {"serial1", "serial2", "serial3"}
        )
        self.assertFalse(moves_with_sn.trace_ids.company_id)

    def test_inventory_adjustment_tracked_product_multilocation(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ],
            }
        )
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )
        lot_1 = self.env["product.trace"].create(
            {"product_id": self.productlot1.id, "name": "lot1"}
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.shelf1, 3, trace_id=lot_1
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.shelf2, 5, trace_id=lot_1
        )
        quants = self.env["stock.quant"].search(
            [("product_id", "=", self.productlot1.id)]
        )
        quants.user_id = self.env.user
        quants.inventory_quantity_set = True
        quants.inventory_date = fields.Date.today()
        quants[0].inventory_quantity = 3
        quants[1].inventory_quantity = 0
        for location, numbers in [(self.shelf1, [1, 2, 3]), (self.shelf3, [4, 5])]:
            for n in numbers:
                serial_number = self.env["product.trace"].create(
                    {"product_id": self.productserial1.id, "name": f"sn{n}"}
                )
                self.env["stock.quant"]._update_available_quantity(
                    self.productserial1, location, 1, trace_id=serial_number
                )
        self.start_tour(
            "/odoo/barcode",
            "test_inventory_adjustment_tracked_product_multilocation",
            login="admin",
            timeout=180,
        )

    def test_inventory_adjustment_tracked_product_permissive_quants(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )

        lot1 = self.env["product.trace"].create(
            {
                "name": "lot1",
                "product_id": self.productlot1.id,
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            self.productlot1, self.stock_location, 5
        )
        self.start_tour(
            "/odoo/barcode",
            "test_inventory_adjustment_tracked_product_permissive_quants",
            login="admin",
            timeout=180,
        )

        inventory_moves = self.env["stock.move"].search(
            [("product_id", "=", self.productlot1.id), ("is_inventory", "=", True)]
        )
        inventory_location = self.productlot1.property_stock_inventory
        self.assertEqual(len(inventory_moves), 2)
        self.assertEqual(inventory_moves.mapped("state"), ["done", "done"])
        self.assertEqual(inventory_moves.product_id, self.productlot1)

        self.assertEqual(len(inventory_moves.move_line_ids), 2)
        self.assertRecordValues(
            inventory_moves.move_line_ids,
            [
                {
                    "quantity": 5,
                    "location_id": self.stock_location.id,
                    "location_dest_id": inventory_location.id,
                    "trace_id": False,
                },
                {
                    "quantity": 2,
                    "location_id": inventory_location.id,
                    "location_dest_id": self.stock_location.id,
                    "trace_id": lot1.id,
                },
            ],
        )

    def test_inventory_create_quant(self):
        Quant = self.env["stock.quant"]
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )
        self.start_tour(
            "/odoo/barcode", "test_inventory_create_quant", login="admin", timeout=180
        )

        Quant._remove_zero_quants()
        product1_quant = Quant.search([("product_id", "=", self.product1.id)])
        self.assertEqual(len(product1_quant), 1)
        self.assertEqual(product1_quant.inventory_quantity, 0.0)

        product1_quant.action_validate()
        Quant.invalidate_model()
        Quant._remove_zero_quants()
        product1_quant = Quant.search([("product_id", "=", self.product1.id)])
        self.assertEqual(len(product1_quant), 0)

    def test_inventory_dialog_not_counted_serial_numbers(self):
        self.env["ir.config_parameter"].set_param(
            "stock_barcode.barcode_separator_regex", "[,;]"
        )
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                ],
            }
        )
        Quant = self.env["stock.quant"]
        productserial2 = self.env["product.product"].create(
            {
                "name": "productserial2",
                "is_storable": True,
                "categ_id": self.env.ref("product.product_category_goods").id,
                "barcode": "productserial2",
                "tracking": "serial",
            }
        )
        serial1_sns = self.create_serial_numbers(self.productserial1, 1, 6)
        serial2_sns = self.create_serial_numbers(productserial2, 1, 3)
        for sn in serial1_sns[:3]:
            Quant._update_available_quantity(sn.product_id, self.shelf1, 1, trace_id=sn)
        for sn in serial1_sns[3:] | serial2_sns:
            Quant._update_available_quantity(sn.product_id, self.shelf2, 1, trace_id=sn)
        quants = Quant.search(
            [("product_id", "in", [self.productserial1.id, productserial2.id])]
        )
        wizard_request_count = self.env["wizard.stock.quant.request.count"].create(
            {
                "user_id": self.env.user.id,
                "quant_ids": quants.ids,
                "show_expected_quantity": True,
            }
        )
        wizard_request_count.action_request_count()
        self.start_tour(
            "/odoo/barcode",
            "test_inventory_dialog_not_counted_serial_numbers",
            login="admin",
        )
        self.assertRecordValues(
            quants,
            [
                {
                    "product_id": self.productserial1.id,
                    "trace_id": serial1_sns[0].id,
                    "quantity": 1,
                    "location_id": self.shelf1.id,
                },
                {
                    "product_id": self.productserial1.id,
                    "trace_id": serial1_sns[1].id,
                    "quantity": 1,
                    "location_id": self.shelf1.id,
                },
                {
                    "product_id": self.productserial1.id,
                    "trace_id": serial1_sns[2].id,
                    "quantity": 0,
                    "location_id": self.shelf1.id,
                },
                {
                    "product_id": self.productserial1.id,
                    "trace_id": serial1_sns[3].id,
                    "quantity": 1,
                    "location_id": self.shelf2.id,
                },
                {
                    "product_id": self.productserial1.id,
                    "trace_id": serial1_sns[4].id,
                    "quantity": 1,
                    "location_id": self.shelf2.id,
                },
                {
                    "product_id": self.productserial1.id,
                    "trace_id": serial1_sns[5].id,
                    "quantity": 1,
                    "location_id": self.shelf2.id,
                },
                {
                    "product_id": productserial2.id,
                    "trace_id": serial2_sns[0].id,
                    "quantity": 1,
                    "location_id": self.shelf2.id,
                },
                {
                    "product_id": productserial2.id,
                    "trace_id": serial2_sns[1].id,
                    "quantity": 1,
                    "location_id": self.shelf2.id,
                },
                {
                    "product_id": productserial2.id,
                    "trace_id": serial2_sns[2].id,
                    "quantity": 1,
                    "location_id": self.shelf2.id,
                },
            ],
        )

    def test_inventory_image_visible_for_quant(self):
        img_url = "stock_barcode/static/img/barcode.png"
        img_content = base64.b64encode(file_open(img_url, "rb").read())
        self.product1.image_1920 = img_content
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 4
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 4
        )
        quants = self.env["stock.quant"].search(
            [("product_id", "in", [self.product1.id, self.product2.id])]
        )
        wizard_request_count = self.env["wizard.stock.quant.request.count"].create(
            {
                "user_id": self.env.user.id,
                "quant_ids": quants.ids,
                "show_expected_quantity": False,
            }
        )
        wizard_request_count.action_request_count()
        self.start_tour(
            "/odoo/barcode/",
            "test_inventory_image_visible_for_quant",
            login="admin",
            timeout=180,
        )

    def test_inventory_nomenclature(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes.default_barcode_nomenclature"
        )

        product_weight = self.env["product.product"].create(
            {
                "name": "product_weight",
                "is_storable": True,
                "barcode": "2145631000000",
            }
        )

        self.start_tour(
            "/odoo/barcode", "test_inventory_nomenclature", login="admin", timeout=180
        )
        quantity = self.env["stock.move.line"].search(
            [
                ("product_id", "=", product_weight.id),
                ("state", "=", "done"),
                ("location_id", "=", product_weight.property_stock_inventory.id),
            ]
        )

        self.assertEqual(quantity.qty_done, 12.35)

    def test_inventory_package(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_tracking_lot").id)]}
        )

        pack = self.env["stock.package"].create(
            {
                "name": "PACK001",
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 7, package_id=pack
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 3, package_id=pack
        )

        self.start_tour(
            "/odoo/barcode", "test_inventory_package", login="admin", timeout=180
        )

        self.assertDictEqual(
            {q.product_id: q.quantity for q in pack.quant_ids},
            {self.product1: 7, self.product2: 21},
        )

    def test_inventory_packaging(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("base.group_uom").id)]}
        )
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )

        pack_15 = self.env["uom.uom"].create(
            {
                "name": "Pack of 15",
                "relative_factor": 15,
                "relative_uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )
        self.product1.uom_ids = pack_15
        self.env["product.uom"].create(
            {
                "uom_id": pack_15.id,
                "product_id": self.product1.id,
                "barcode": "pack007",
            }
        )
        self.start_tour(
            "/odoo/barcode", "test_inventory_packaging", login="admin", timeout=180
        )
        self.assertEqual(self.product1.qty_available, 15.0)

    def test_inventory_serial_product_packaging(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_production_lot").id),
                    Command.link(self.env.ref("base.group_uom").id),
                ],
            }
        )
        pack_3 = self.env["uom.uom"].create(
            {
                "name": "Product Serial 1 Packaging",
                "relative_factor": 3,
                "relative_uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )
        self.productserial1.uom_ids = pack_3
        self.env["product.uom"].create(
            {
                "uom_id": pack_3.id,
                "product_id": self.productserial1.id,
                "barcode": "PCK3",
            }
        )

        self.start_tour(
            "/odoo/barcode",
            "test_inventory_serial_product_packaging",
            login="admin",
            timeout=180,
        )

    def test_inventory_packaging_button(self):
        self.product1.name = "Lovely Product"
        self.product1.uom_ids = self.env["uom.uom"].create(
            {
                "name": "LP x15",
                "relative_factor": 15,
                "relative_uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )
        self.start_tour(
            "/odoo/barcode",
            "test_inventory_packaging_button",
            login="admin",
            timeout=180,
        )
        quant = self.env["stock.quant"].search(
            [("product_id", "=", self.product1.id)], limit=1
        )
        self.assertEqual(quant.inventory_quantity, 15.0)

    def test_inventory_packaging_location(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("base.group_uom").id)]}
        )

        self.env["product.uom"].create(
            {
                "product_id": self.product1.id,
                "uom_id": self.env.ref("base.product_uom_dozen").id,
                "barcode": "DOZENPACK001",
            }
        )

        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 40.0
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf2, 80.0
        )

        self.start_tour(
            "/odoo/barcode", "test_inventory_packaging_location", login="admin"
        )
        self.browser_size = "375x667"
        self.touch_enabled = True
        self.start_tour(
            "/odoo/barcode", "test_inventory_packaging_location", login="admin"
        )

    def test_inventory_owner_scan_package(self):
        group_owner = self.env.ref("stock.group_tracking_owner")
        group_pack = self.env.ref("stock.group_tracking_lot")
        self.env.user.write({"group_ids": [Command.link(group_pack.id)]})
        self.env.user.write({"group_ids": [Command.link(group_owner.id)]})

        self.env["stock.quant"]._update_available_quantity(
            self.product1,
            self.stock_location,
            7,
            package_id=self.package,
            owner_id=self.owner,
        )

        self.start_tour(
            "/odoo/barcode",
            "test_inventory_owner_scan_package",
            login="admin",
            timeout=180,
        )

        inventory_moves = self.env["stock.move"].search(
            [("product_id", "=", self.product1.id), ("is_inventory", "=", True)]
        )
        self.assertEqual(len(inventory_moves), 1)
        self.assertEqual(inventory_moves.state, "done")
        self.assertEqual(inventory_moves.move_line_ids.owner_id.id, self.owner.id)

    def test_inventory_setting_count_entire_locations_on(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        Quant = self.env["stock.quant"]

        lots = self.env["product.trace"].create(
            [
                {
                    "name": f"lot{i}",
                    "product_id": self.productlot1.id,
                }
                for i in range(1, 5)
            ]
        )
        shelf1_serial_numbers = self.create_serial_numbers(self.productserial1, 1, 3)
        shelf2_serial_numbers = self.create_serial_numbers(self.productserial1, 4, 3)

        Quant._update_available_quantity(self.product1, self.shelf1, 10)
        Quant._update_available_quantity(self.product2, self.shelf1, 20)
        Quant._update_available_quantity(
            self.productlot1, self.shelf1, 3, trace_id=lots[0]
        )
        Quant._update_available_quantity(
            self.productlot1, self.shelf1, 4, trace_id=lots[1]
        )
        for sn in shelf1_serial_numbers:
            Quant._update_available_quantity(
                self.productserial1, self.shelf1, 1, trace_id=sn
            )
        Quant._update_available_quantity(self.product1, self.shelf2, 30)
        Quant._update_available_quantity(
            self.productlot1, self.shelf2, 5, trace_id=lots[2]
        )
        Quant._update_available_quantity(
            self.productlot1, self.shelf2, 2, trace_id=lots[3]
        )
        for sn in shelf2_serial_numbers:
            Quant._update_available_quantity(
                self.productserial1, self.shelf2, 1, trace_id=sn
            )

        quants = Quant.search(
            [
                ("product_id", "=", self.product1.id),
                ("location_id", "=", self.shelf1.id),
            ]
        )
        wizard_request_count = self.env["wizard.stock.quant.request.count"].create(
            {
                "user_id": self.env.user.id,
                "quant_ids": quants.ids,
                "show_expected_quantity": True,
            }
        )
        wizard_request_count.action_request_count()
        self.start_tour(
            "/odoo/barcode",
            "test_inventory_setting_count_entire_locations_on",
            login="admin",
            timeout=180,
        )

    def test_inventory_setting_count_entire_locations_off(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )
        Quant = self.env["stock.quant"]

        Quant._update_available_quantity(self.product1, self.shelf1, 10)
        Quant._update_available_quantity(self.product2, self.shelf1, 20)
        Quant._update_available_quantity(self.product1, self.shelf2, 30)

        quants = Quant.search(
            [
                ("product_id", "=", self.product1.id),
                ("location_id", "=", self.shelf1.id),
            ]
        )
        wizard_request_count = self.env["wizard.stock.quant.request.count"].create(
            {
                "user_id": self.env.user.id,
                "quant_ids": quants.ids,
                "show_expected_quantity": True,
            }
        )
        wizard_request_count.action_request_count()
        self.start_tour(
            "/odoo/barcode",
            "test_inventory_setting_count_entire_locations_off",
            login="admin",
            timeout=180,
        )

    def test_inventory_setting_show_quantity_to_count(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_production_lot").id),
                ],
            }
        )
        Quant = self.env["stock.quant"]

        serial_numbers = self.create_serial_numbers(self.productserial1, 1, 3)
        lots = self.env["product.trace"].create(
            [
                {
                    "name": lot_name,
                    "product_id": self.productlot1.id,
                }
                for lot_name in ["lot1", "lot2"]
            ]
        )

        for sn in serial_numbers:
            Quant._update_available_quantity(
                self.productserial1, self.stock_location, 1, trace_id=sn
            )
        Quant._update_available_quantity(
            self.productlot1, self.stock_location, 3, trace_id=lots[0]
        )
        Quant._update_available_quantity(
            self.productlot1, self.stock_location, 4, trace_id=lots[1]
        )
        Quant._update_available_quantity(self.product1, self.stock_location, 5)

        quants = Quant.search(
            [
                (
                    "product_id",
                    "in",
                    [self.product1.id, self.productlot1.id, self.productserial1.id],
                )
            ]
        )
        wizard_request_count = self.env["wizard.stock.quant.request.count"].create(
            {
                "user_id": self.env.user.id,
                "quant_ids": quants.ids,
                "show_expected_quantity": True,
            }
        )
        wizard_request_count.action_request_count()

        self.start_tour(
            "/odoo/barcode",
            "test_inventory_setting_show_quantity_to_count_on",
            login="admin",
            timeout=180,
        )
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "False"
        )
        self.start_tour(
            "/odoo/barcode",
            "test_inventory_setting_show_quantity_to_count_off",
            login="admin",
            timeout=180,
        )

    def test_inventory_using_buttons(self):
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.stock_location, 10
        )

        self.start_tour(
            "/odoo/barcode", "test_inventory_using_buttons", login="admin", timeout=180
        )
        product1_quant = self.env["stock.quant"].search(
            [("product_id", "=", self.product1.id), ("quantity", ">", 0)]
        )
        self.assertEqual(len(product1_quant), 1)
        self.assertEqual(product1_quant.quantity, 1.0)
        self.assertEqual(product1_quant.location_id.id, self.stock_location.id)

        productlot1_quant = self.env["stock.quant"].search(
            [("product_id", "=", self.productlot1.id), ("quantity", ">", 0)]
        )
        self.assertEqual(len(productlot1_quant), 1)
        self.assertEqual(productlot1_quant.quantity, 1.0)
        self.assertEqual(productlot1_quant.trace_id.name, "toto-42")
        self.assertEqual(productlot1_quant.location_id.id, self.stock_location.id)
        inventory_move_line = self.env["stock.move.line"].search(
            [("product_id", "=", self.product1.id), ("is_inventory", "=", True)],
            limit=1,
        )
        self.assertEqual(inventory_move_line.reference, "Very important reason")

    def test_inventory_adjustment_with_no_internal_location_quant(self):
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id)
                ]
            }
        )

        self.env["stock.quant"].create(
            {
                "product_id": self.product1.id,
                "location_id": self.env.ref("stock.stock_location_customers").id,
                "quantity": -1,
            }
        )

        self.env["stock.quant"].create(
            {
                "product_id": self.product1.id,
                "location_id": self.product1.property_stock_inventory.id,
                "quantity": 1,
            }
        )

        self.start_tour(
            "/odoo/barcode",
            "test_inventory_adjustment_with_no_internal_location_quant",
            login="admin",
        )

        inventory_moves = self.env["stock.move"].search(
            [("product_id", "=", self.product1.id), ("is_inventory", "=", True)]
        )
        self.assertEqual(len(inventory_moves), 1)
        self.assertEqual(inventory_moves.quantity, 1.0)
        self.assertEqual(inventory_moves.state, "done")
        self.assertEqual(inventory_moves.location_id.name, "Inventory adjustment")
        self.assertEqual(inventory_moves.location_dest_id.name, "Stock")

        quants = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product1.id),
                ("location_id.usage", "=", "internal"),
            ]
        )
        self.assertEqual(quants.quantity, 1.0)
        self.assertEqual(quants.inventory_quantity, 0)
        self.assertEqual(quants.inventory_diff_quantity, 0)

    def test_rfid_inventory_scan_sgtin(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )

        product_common_vals = {
            "is_storable": True,
            "uom_id": self.env.ref("base.product_uom_unit").id,
        }
        products = self.env["product.product"].create(
            [
                {
                    **product_common_vals,
                    "name": product_name,
                    "barcode": barcode,
                }
                for (product_name, barcode) in [
                    ("Lunch box", "2300001000015"),
                    ("French wine", "2300001000084"),
                    ("Japanese wine", "2300001000121"),
                    ("Large plate", "5468123001239"),
                    ("Inox knife", "5468123002465"),
                ]
            ]
        )
        tracked_products = self.env["product.product"].create(
            [
                {
                    **product_common_vals,
                    "name": product_name,
                    "is_storable": True,
                    "tracking": "serial",
                    "barcode": barcode,
                }
                for (product_name, barcode) in [
                    ("Handmade argyle plate", "8765432100002"),
                    ("Chief suit", "8765432300044"),
                ]
            ]
        )
        p1_serial_numbers = self.env["product.trace"].create(
            [
                {
                    "name": str(i).rjust(5, "0"),
                    "product_id": tracked_products[0].id,
                }
                for i in range(128, 134)
            ]
        )
        p2_serial_numbers = self.env["product.trace"].create(
            [
                {
                    "name": str(i),
                    "product_id": tracked_products[1].id,
                }
                for i in [12, 10, 15, 16, 9]
            ]
        )
        self.env["stock.quant"]._update_available_quantity(
            products[0], self.stock_location, 12
        )
        self.env["stock.quant"]._update_available_quantity(
            products[3], self.stock_location, 35
        )
        self.env["stock.quant"]._update_available_quantity(
            products[4], self.stock_location, 11
        )
        for serial_number in p1_serial_numbers | p2_serial_numbers:
            self.env["stock.quant"]._update_available_quantity(
                serial_number.product_id, self.stock_location, 1, trace_id=serial_number
            )

        self1 = self
        get_specific_barcode_data_orig = (
            StockBarcodeController.get_specific_barcode_data
        )

        @http.route(
            "/stock_barcode/get_specific_barcode_data", type="jsonrpc", auth="user"
        )
        def mocked_data_batch_method(self, **kwargs):
            if self1.call_count == 0:
                self1.assertEqual(
                    list(kwargs["barcodes_by_model"].keys()),
                    ["product.product", "product.uom", "product.trace"],
                )
            elif self1.call_count == 1:
                self1.assertEqual(
                    list(kwargs["barcodes_by_model"].keys()), ["product.trace"]
                )
            self1.call_count += 1
            return get_specific_barcode_data_orig(self, **kwargs)

        with patch.object(
            StockBarcodeController,
            "get_specific_barcode_data",
            mocked_data_batch_method,
        ):
            self.start_tour(
                "/odoo/barcode",
                "test_rfid_inventory_scan_sgtin",
                login="admin",
                timeout=180,
            )
            self.assertEqual(self.call_count, 2)

    def test_inventory_count_with_line_deletion(self):
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 5
        )
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )
        self.start_tour(
            "/odoo/barcode", "test_inventory_count_with_line_deletion", login="admin"
        )
        quant = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.product1.id),
                ("location_id", "=", self.stock_location.id),
            ]
        )
        self.assertEqual(quant.quantity, 5, "deleting a count must not apply it")

    def test_gs1_inventory_gtin_8(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )

        product = self.env["product.product"].create(
            {
                "name": "PRO_GTIN_8",
                "is_storable": True,
                "barcode": "82655853",
                "uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )

        self.start_tour(
            "/odoo/barcode", "test_gs1_inventory_gtin_8", login="admin", timeout=180
        )

        move_line = self.env["stock.move.line"].search(
            [
                ("product_id", "=", product.id),
                ("state", "=", "done"),
                ("location_id", "=", product.property_stock_inventory.id),
            ]
        )
        self.assertEqual(move_line.qty_done, 78)

    def test_gs1_inventory_product_units(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )

        product = self.env["product.product"].create(
            {
                "name": "PRO_GTIN_8",
                "is_storable": True,
                "barcode": "82655853",
                "uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )

        self.start_tour(
            "/odoo/barcode",
            "test_gs1_inventory_product_units",
            login="admin",
            timeout=180,
        )

        quantity = self.env["stock.move.line"].search(
            [
                ("product_id", "=", product.id),
                ("state", "=", "done"),
                ("location_id", "=", product.property_stock_inventory.id),
            ]
        )

        self.assertEqual(quantity.qty_done, 102)

    def test_gs1_inventory_package(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(self.env.ref("stock.group_stock_multi_locations").id),
                    Command.link(self.env.ref("stock.group_tracking_lot").id),
                ]
            }
        )
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )

        product = self.env["product.product"].create(
            {
                "name": "PRO_GTIN_8",
                "is_storable": True,
                "barcode": "82655853",
                "uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )

        pack_1 = self.env["stock.package"].create({"name": "987654123487568456"})
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.shelf1, 8, package_id=pack_1
        )
        pack_2 = self.env["stock.package"].create({"name": "487325612456785124"})
        self.env["stock.quant"]._update_available_quantity(
            self.product2, self.shelf2, 6, package_id=pack_2
        )

        self.start_tour(
            "/odoo/barcode", "test_gs1_inventory_package", login="admin", timeout=180
        )

        pack_3 = self.env["stock.package"].search([("name", "=", "122333444455555670")])
        self.assertEqual(pack_3.location_id.id, self.shelf2.id)
        self.assertEqual(pack_3.quant_ids.product_id.ids, [product.id])

    def test_gs1_inventory_lot_serial(self):
        self.env.user.write(
            {"group_ids": [Command.link(self.env.ref("stock.group_production_lot").id)]}
        )
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        self.env.company.barcodes_config_id.nomenclature_id.gs1_separator_fnc1 = (
            r"(Alt029|#|\x1D|~)"
        )

        product_lot = self.env["product.product"].create(
            {
                "name": "PRO_GTIN_12_lot",
                "is_storable": True,
                "barcode": "111155555717",
                "uom_id": self.env.ref("base.product_uom_unit").id,
                "tracking": "lot",
            }
        )

        product_serial = self.env["product.product"].create(
            {
                "name": "PRO_GTIN_14_serial",
                "is_storable": True,
                "barcode": "15222222222219",
                "uom_id": self.env.ref("base.product_uom_unit").id,
                "tracking": "serial",
            }
        )

        self.start_tour(
            "/odoo/barcode", "test_gs1_inventory_lot_serial", login="admin", timeout=180
        )

        smls_lot = self.env["stock.move.line"].search(
            [
                ("product_id", "=", product_lot.id),
                ("state", "=", "done"),
                ("location_id", "=", product_lot.property_stock_inventory.id),
            ]
        )
        self.assertEqual(len(smls_lot), 3)
        self.assertEqual(smls_lot[0].qty_done, 10)
        self.assertEqual(smls_lot[1].qty_done, 15)
        self.assertEqual(smls_lot[2].qty_done, 20)
        self.assertEqual(
            smls_lot.trace_id.mapped("name"), ["LOT-AAA", "LOT-AAB", "LOT-AAC"]
        )

        smls_serial = self.env["stock.move.line"].search(
            [
                ("product_id", "=", product_serial.id),
                ("state", "=", "done"),
                ("location_id", "=", product_serial.property_stock_inventory.id),
            ]
        )
        self.assertEqual(len(smls_serial), 5)
        self.assertEqual(smls_serial[0].qty_done, 1)
        self.assertEqual(smls_serial[1].qty_done, 1)
        self.assertEqual(smls_serial[2].qty_done, 1)
        self.assertEqual(smls_serial[3].qty_done, 20)
        self.assertEqual(smls_serial[4].qty_done, 1)
        self.assertEqual(
            smls_serial.trace_id.mapped("name"),
            ["Serial1", "Serial2", "Serial3", "Serial4"],
        )

    def test_scan_product_lot_with_package(self):
        self.env["res.config.settings"].create(
            {"group_stock_tracking_lot": True}
        ).execute()
        product = self.env["product.product"].create(
            {
                "name": "Product",
                "is_storable": True,
                "tracking": "lot",
            }
        )
        self.env["stock.quant"].create(
            {
                "product_id": product.id,
                "location_id": self.stock_location.id,
                "quantity": 10,
                "package_id": self.env["stock.package"]
                .create(
                    {
                        "name": "Package-test",
                    }
                )
                .id,
                "trace_id": self.env["product.trace"]
                .create(
                    {
                        "name": "Lot-test",
                        "product_id": product.id,
                    }
                )
                .id,
            }
        )
        self.assertEqual(product.qty_available, 10)
        self.start_tour("/odoo", "stock_barcode_package_with_lot", login="admin")
        quants = self.env["stock.quant"].search([("product_id", "=", product.id)])
        self.assertEqual(
            [(q.quantity, q.package_id.name, q.trace_id.name) for q in quants],
            [(10, "Package-test", "Lot-test")],
            "the scanned lot is counted in its package, not as a new unpacked quant",
        )

    def test_inventory_count_lot_split_in_packages(self):
        grp_multi_loc = self.env.ref("stock.group_stock_multi_locations")
        grp_lot = self.env.ref("stock.group_production_lot")
        grp_pack = self.env.ref("stock.group_tracking_lot")
        self.env.user.write(
            {
                "group_ids": [
                    Command.link(grp_pack.id),
                    Command.link(grp_multi_loc.id),
                    Command.link(grp_lot.id),
                ]
            }
        )
        self.env["ir.config_parameter"].set_param(
            "stock.show_expected_quantity_count", "True"
        )
        shelf1 = self.env["stock.location"].create(
            {
                "name": "Shelf 11",
                "barcode": "Shelf11",
                "location_id": self.warehouse.lot_stock_id.id,
            }
        )
        product = self.env["product.product"].create(
            {
                "name": "Product",
                "is_storable": True,
                "tracking": "lot",
            }
        )
        lot = self.env["product.trace"].create(
            {
                "name": "Lot-test",
                "product_id": product.id,
            }
        )
        pack1 = self.env["stock.package"].create(
            {
                "name": "Pack1",
            }
        )
        pack2 = self.env["stock.package"].create(
            {
                "name": "Pack2",
            }
        )
        self.env["stock.quant"]._update_available_quantity(
            product, shelf1, 5, trace_id=lot, package_id=pack1
        )
        self.env["stock.quant"]._update_available_quantity(
            product, shelf1, 5, trace_id=lot, package_id=pack2
        )
        action_id = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        url = "/web#action=" + str(action_id.id)
        self.start_tour(url, "test_correct_inventory_with_packages", login="admin")
