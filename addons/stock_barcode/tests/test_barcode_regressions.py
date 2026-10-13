
import base64
import io
import re
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.modules.module import Manifest
from odoo.tests import TransactionCase, tagged
from odoo.tools.files import file_path

from odoo.addons.barcodes.models.ir_http import DEFAULT_MAX_TIME_BETWEEN_KEYS_MS
from odoo.addons.stock_barcode.models.epc_encoder import EpcData, EpcScheme


@tagged("post_install", "-at_install")
class TestStockBarcodeRegressions(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.stock_location = cls.warehouse.lot_stock_id
        cls.shelf = cls.env["stock.location"].create(
            {
                "name": "Regression Shelf",
                "location_id": cls.stock_location.id,
                "barcode": "REG-SHELF",
            }
        )
        cls.tracked_product = cls.env["product.product"].create(
            {
                "name": "Regression tracked product",
                "is_storable": True,
                "tracking": "lot",
                "barcode": "REG-TRACKED",
            }
        )

    def _quant_command(self, location, lot_name):
        return [
            0,
            0,
            {
                "product_id": self.tracked_product.id,
                "location_id": location.id,
                "lot_name": lot_name,
                "inventory_quantity": 1,
                "inventory_quantity_set": True,
                "user_id": self.env.user.id,
                "inventory_date": fields.Date.context_today(self.env.user),
            },
        ]

    def test_barcode_write_reuses_a_lot_within_one_batch(self):
        Lot = self.env["product.trace"]
        before = Lot.search_count([("product_id", "=", self.tracked_product.id)])
        self.env["stock.quant"].barcode_write(
            [
                self._quant_command(self.stock_location, "REG-LOT-1"),
                self._quant_command(self.shelf, "REG-LOT-1"),
            ]
        )
        lots = Lot.search(
            [("product_id", "=", self.tracked_product.id), ("name", "=", "REG-LOT-1")]
        )
        self.assertEqual(len(lots), 1, "both lines must share one lot")
        self.assertEqual(
            Lot.search_count([("product_id", "=", self.tracked_product.id)]), before + 1
        )
        quants = self.env["stock.quant"].search(
            [("product_id", "=", self.tracked_product.id), ("trace_id", "=", lots.id)]
        )
        self.assertEqual(
            set(quants.mapped("location_id").ids),
            {self.stock_location.id, self.shelf.id},
        )

    def test_barcode_write_reuses_an_existing_lot(self):
        lot = self.env["product.trace"].create(
            {"name": "REG-LOT-2", "product_id": self.tracked_product.id}
        )
        self.env["stock.quant"].barcode_write(
            [self._quant_command(self.shelf, "REG-LOT-2")]
        )
        self.assertEqual(
            self.env["product.trace"].search_count(
                [
                    ("product_id", "=", self.tracked_product.id),
                    ("name", "=", "REG-LOT-2"),
                ]
            ),
            1,
        )
        quant = self.env["stock.quant"].search(
            [
                ("product_id", "=", self.tracked_product.id),
                ("location_id", "=", self.shelf.id),
            ]
        )
        self.assertEqual(quant.trace_id, lot)

    def test_usable_packages_are_bounded(self):
        Package = self.env["stock.package"]
        Package.create([{"name": f"REG-PKG-{i:03d}"} for i in range(5)])
        self.env["ir.config_parameter"].sudo().set_param(
            "stock_barcode.usable_packages_limit", "3"
        )
        self.assertEqual(len(Package._get_usable_packages()), 3)
        self.env["ir.config_parameter"].sudo().set_param(
            "stock_barcode.usable_packages_limit", False
        )
        with patch.object(type(Package), "USABLE_PACKAGES_LIMIT", 2):
            self.assertEqual(len(Package._get_usable_packages()), 2)

    def test_has_image_follows_the_image(self):
        product = self.env["product.product"].create({"name": "Regression image probe"})
        self.assertFalse(product.has_image)
        product.image_1920 = self._one_pixel_png()
        self.assertTrue(product.has_image)

    def test_scrap_scan_of_a_lot_name_shared_across_products(self):
        other_product = self.env["product.product"].create(
            {
                "name": "Regression tracked product 2",
                "is_storable": True,
                "tracking": "lot",
            }
        )
        self.env["product.trace"].create(
            [
                {"name": "REG-SHARED", "product_id": self.tracked_product.id},
                {"name": "REG-SHARED", "product_id": other_product.id},
            ]
        )
        scrap = self.env["stock.scrap"].create(
            {"product_id": self.tracked_product.id, "scrap_qty": 1}
        )
        scrap.on_barcode_scanned("REG-SHARED")
        self.assertEqual(
            scrap.trace_id.product_id,
            self.tracked_product,
            "the lot of the product already on the scrap wins",
        )

    def test_epc_scheme_name_is_validated(self):
        with self.assertRaises(UserError):
            EpcScheme(self.env, "not-a-scheme")
        with self.assertRaises(UserError):
            EpcScheme(self.env, "x'] | //*[1]|//scheme[@name='sgtin-96")
        self.assertIn("sgtin-96", EpcData.scheme_names())

    def test_epc_partition_ai_is_found_in_any_position(self):
        scheme = EpcScheme(self.env, "sgtin-96")
        forward = scheme.encode("(01) 00000076543210 (21) 42", 1, 7)
        scheme = EpcScheme(self.env, "sgtin-96")
        reversed_ = scheme.encode("(21) 42 (01) 00000076543210", 1, 7)
        self.assertEqual(forward, reversed_)
        self.assertNotIn("error", forward.lower())

    def test_epc_write_bits_rejects_a_non_integer(self):
        with self.assertRaises(ValueError):
            EpcData.write_bits("not an int", 8)

    def test_epc_encode_partial_refuses_reserved_fields(self):
        scheme = EpcScheme(self.env, "sgtin-96")
        with self.assertRaises(UserError):
            scheme.encode_partial("header", 1)

    def _one_pixel_png(self):
        image = Image.new("RGB", (1, 1), color="red")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue())


@tagged("post_install", "-at_install")
class TestTourHelperIsReachable(TransactionCase):
    HELPER = "stock_barcode/static/tests/tours/running_tour_action_helper.js"

    IMPORTS_HELPER = re.compile(
        r'^\s*import\s+["\']\.{1,2}/(?:[\w./-]*/)?running_tour_action_helper(?:\.js)?["\']\s*;?\s*$',
        re.MULTILINE,
    )

    def test_tour_action_helper_is_reachable_from_the_tours_bundle(self):
        tours = Path(file_path("stock_barcode/static/tests/tours", ("",)))
        importers = sorted(
            path.name
            for path in tours.rglob("*.js")
            if path.name != "running_tour_action_helper.js"
            and self.IMPORTS_HELPER.search(path.read_text(encoding="utf-8"))
        )
        self.assertTrue(
            importers,
            "no file under stock_barcode/static/tests/tours imports "
            "running_tour_action_helper.js for its side effect. Bundle "
            "membership is not reachability: under native ESM the browser "
            "evaluates only what the bundle's entry points statically import, "
            "so without an import the `scan` action is never registered and "
            "every tour dies at its first scan step -- while still running "
            "every step that does not scan, which is why this is asserted "
            "here rather than left to the browser suite.",
        )

    def test_tour_action_helper_is_named_in_no_bundle(self):
        assets = Manifest.for_addon("stock_barcode")["assets"]
        declaring = sorted(
            bundle
            for bundle, entries in assets.items()
            if any(entry == self.HELPER for entry in entries if isinstance(entry, str))
        )
        self.assertEqual(
            declaring,
            [],
            "running_tour_action_helper.js must not be named in any bundle "
            "explicitly -- it rides the `tests/tours/**/*` glob in "
            "`web.assets_tests` and is reached by import. Naming it in a second "
            "bundle (it used to be in `web_tour.automatic`) means both bundles "
            "carry it, it is evaluated twice on any page running a tour, and "
            "every registry add fires twice.",
        )


@tagged("post_install", "-at_install")
class TestStockBarcodeRegressions20260928(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.supplier_location = cls.env.ref("stock.stock_location_suppliers")
        cls.stock_location = cls.env.ref("stock.stock_location_stock")
        cls.receipt_type = cls.env.ref("stock.picking_type_in")

    def _receipt(self, products, qty=10):
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": self.receipt_type.id,
                "location_id": self.supplier_location.id,
                "location_dest_id": self.stock_location.id,
            }
        )
        moves = self.env["stock.move"].create(
            [
                {
                    "product_id": product.id,
                    "product_uom_qty": qty,
                    "product_uom_id": product.uom_id.id,
                    "location_id": self.supplier_location.id,
                    "location_dest_id": self.stock_location.id,
                    "picking_id": picking.id,
                }
                for product in products
            ]
        )
        picking.action_confirm()
        return picking, moves

    def test_partial_move_count_is_not_offset_by_the_empty_moves(self):
        products = self.env["product.product"].create(
            [{"name": f"Partial count {name}", "is_storable": True} for name in "ABC"]
        )
        picking, moves = self._receipt(products)
        moves[:2].write({"quantity": 0, "picked": False})
        moves[2].write({"quantity": 4, "picked": True})
        wizard = self.env["wizard.stock.picking.validate.partial"].create(
            {"pick_ids": [Command.set(picking.ids)]}
        )
        self.assertEqual(wizard.empty_move_count, 2)
        self.assertEqual(wizard.partial_move_count, 1)

    def test_filter_on_barcode_survives_an_unparsable_gs1_barcode(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        result = (
            self.env["stock.picking"]
            .with_context(active_id=self.receipt_type.id)
            .filter_on_barcode("17261399")
        )
        self.assertIn("warning", result)

    def test_new_after_a_barcode_filter_opens_the_barcode_app(self):
        product = self.env["product.product"].create(
            {"name": "Filter product", "is_storable": True, "barcode": "FILTER-1"}
        )
        self._receipt(product)
        result = (
            self.env["stock.picking"]
            .with_context(active_id=self.receipt_type.id)
            .filter_on_barcode("FILTER-1")
        )
        context = result["action"]["context"]
        action = (
            self.env["stock.picking"].with_context(context).action_view_new_picking()
        )
        self.assertEqual(action["tag"], "stock_barcode_client_action")

    def test_epc_scheme_reencodes_with_another_company_prefix_length(self):
        element = "(01) 80614141123458 (21) 6789"
        reused = EpcScheme(self.env, "sgtin-96")
        reused.encode(element, 1, 7)
        self.assertEqual(
            reused.encode(element, 1, 8),
            EpcScheme(self.env, "sgtin-96").encode(element, 1, 8),
        )

    def test_line_quants_stay_within_their_own_picking_location(self):
        product = self.env["product.product"].create(
            {"name": "Two-shelf product", "is_storable": True}
        )
        shelves = self.env["stock.location"].create(
            [
                {"name": f"Shelf {name}", "location_id": self.stock_location.id}
                for name in "AB"
            ]
        )
        Quant = self.env["stock.quant"]
        for shelf in shelves:
            Quant._update_available_quantity(product, shelf, 5)
        internal_type = self.env.ref("stock.picking_type_internal")
        lines = self.env["stock.move.line"]
        for shelf in shelves:
            picking = self.env["stock.picking"].create(
                {
                    "picking_type_id": internal_type.id,
                    "location_id": shelf.id,
                    "location_dest_id": self.stock_location.id,
                }
            )
            self.env["stock.move"].create(
                {
                    "product_id": product.id,
                    "product_uom_qty": 1,
                    "product_uom_id": product.uom_id.id,
                    "location_id": shelf.id,
                    "location_dest_id": self.stock_location.id,
                    "picking_id": picking.id,
                }
            )
            picking.action_confirm()
            picking.action_assign()
            lines |= picking.move_line_ids
        lines.invalidate_recordset(["product_stock_quant_ids"])
        for line, shelf in zip(lines, shelves, strict=True):
            self.assertEqual(line.product_stock_quant_ids.location_id, shelf)

    def test_quant_payload_carries_every_ancestor_package(self):
        Package = self.env["stock.package"]
        outer = Package.create({"name": "OUTER"})
        middle = Package.create({"name": "MIDDLE", "parent_package_id": outer.id})
        inner = Package.create({"name": "INNER", "parent_package_id": middle.id})
        product = self.env["product.product"].create(
            {"name": "Nested product", "is_storable": True}
        )
        self.env["stock.quant"]._update_available_quantity(
            product, self.stock_location, 1, package_id=inner
        )
        quant = self.env["stock.quant"].search(
            [("product_id", "=", product.id), ("package_id", "=", inner.id)]
        )
        payload = quant.get_stock_barcode_data_records()["records"]["stock.package"]
        self.assertEqual({p["id"] for p in payload}, {outer.id, middle.id, inner.id})

    def test_destination_packages_are_bounded(self):
        Package = self.env["stock.package"]
        packages = Package.create([{"name": f"DEST-PKG-{i}"} for i in range(3)])
        product = self.env["product.product"].create(
            {"name": "Packed product", "is_storable": True}
        )
        for package in packages:
            self.env["stock.quant"]._update_available_quantity(
                product, self.stock_location, 1, package_id=package
            )
        self.env["ir.config_parameter"].sudo().set_param(
            "stock_barcode.usable_packages_limit", "2"
        )
        located = (
            Package.with_context(pack_locs=self.stock_location.ids)
            ._get_usable_packages()
            .filtered("location_id")
        )
        self.assertEqual(len(located), 2)

    def test_removing_a_count_keeps_the_stock(self):
        product = self.env["product.product"].create(
            {"name": "Counted product", "is_storable": True}
        )
        Quant = self.env["stock.quant"].with_context(inventory_mode=True)
        Quant._update_available_quantity(product, self.stock_location, 5)
        quant = Quant.search([("product_id", "=", product.id)])
        quant.inventory_quantity = 0
        quant.action_barcode_remove_count()
        self.assertEqual(quant.quantity, 5)
        self.assertFalse(quant.inventory_quantity_set)
        self.assertFalse(
            self.env["stock.move"].search_count(
                [("product_id", "=", product.id), ("is_inventory", "=", True)]
            )
        )

    def test_removing_a_count_drops_a_quant_created_to_be_counted(self):
        product = self.env["product.product"].create(
            {"name": "Counted nowhere", "is_storable": True}
        )
        quant = (
            self.env["stock.quant"]
            .with_context(inventory_mode=True)
            .create(
                {
                    "product_id": product.id,
                    "location_id": self.stock_location.id,
                    "inventory_quantity": 0,
                }
            )
        )
        quant.action_barcode_remove_count()
        self.assertFalse(quant.exists())

    def test_key_timing_setting_defaults_to_the_scanner_default(self):
        defaults = self.env["res.config.settings"].default_get(
            ["barcode_max_time_between_keys_in_ms"]
        )
        self.assertEqual(
            defaults["barcode_max_time_between_keys_in_ms"],
            DEFAULT_MAX_TIME_BETWEEN_KEYS_MS,
        )


@tagged("post_install", "-at_install")
class TestInventoryPayloadCompleteness(TransactionCase):
    def test_the_initial_load_names_the_products_it_sent_every_quant_of(self):
        stock = (
            self.env["stock.warehouse"]
            .search([("company_id", "=", self.env.company.id)], limit=1)
            .lot_stock_id
        )
        shelf = self.env["stock.location"].create(
            {"name": "Completeness shelf", "location_id": stock.id}
        )
        whole, partial = self.env["product.product"].create(
            [
                {"name": "All sent", "is_storable": True},
                {"name": "Half sent", "is_storable": True},
            ]
        )
        Quant = self.env["stock.quant"]
        for product in (whole, partial):
            for location in (stock, shelf):
                Quant._update_available_quantity(product, location, 2)
        quants = Quant.search([("product_id", "in", (whole | partial).ids)])
        sent = quants.filtered(
            lambda q: q.product_id == whole or q.location_id == stock
        )
        self.assertEqual(sent._get_products_with_all_quants(), [whole.id])
        self.assertEqual(Quant._get_products_with_all_quants(), [])
