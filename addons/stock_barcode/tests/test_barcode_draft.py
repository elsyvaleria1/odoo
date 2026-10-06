from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, tagged

from .test_barcode_client_action import TestBarcodeClientAction


@tagged("post_install", "-at_install")
class TestBarcodeDraftPicking(HttpCase):
    """Opening an operation type in the barcode app used to create its picking at once: every
    open that was left without a scan stayed behind as an empty draft and consumed a number
    of the type's sequence."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.picking_type = cls.warehouse.out_type_id
        cls.picking_type.barcode = "DRAFT-OUT"
        cls.product = cls.env["product.product"].create(
            {"name": "Draft product", "is_storable": True}
        )

    def _post(self, route, **params):
        response = self.url_open(
            route,
            data=json_dumps({"jsonrpc": "2.0", "method": "call", "params": params}),
            headers={"Content-Type": "application/json"},
        )
        return response.json()

    def _call(self, route, **params):
        body = self._post(route, **params)
        self.assertNotIn("error", body, body.get("error"))
        return body["result"]

    def _open(self):
        result = self._call("/stock_barcode/scan_from_main_menu", barcode="DRAFT-OUT")
        return result["action"]["context"]

    def _pickings(self):
        return self.env["stock.picking"].search(
            [("picking_type_id", "=", self.picking_type.id)]
        )

    def test_opening_and_leaving_writes_nothing(self):
        self.authenticate("admin", "admin")
        sequence = self.picking_type.sequence_id
        next_number = sequence.number_next_actual
        context = self._open()
        self.assertFalse(context["active_id"])
        data = self._call(
            "/stock_barcode/get_barcode_data",
            model="stock.picking",
            res_id=False,
            draft=context["barcode_draft"],
        )["data"]
        [picking] = data["records"]["stock.picking"]
        self.assertFalse(picking["id"])
        self.assertEqual(picking["picking_type_id"], self.picking_type.id)
        self.assertIn("restrict_scan_source_location", data["config"])
        self.assertFalse(self._pickings())
        sequence.invalidate_recordset()
        self.assertEqual(sequence.number_next_actual, next_number)

    def test_the_first_save_creates_the_picking_once(self):
        self.authenticate("admin", "admin")
        draft = self._open()["barcode_draft"]
        location = self.picking_type.default_location_src_id
        data = self._call(
            "/stock_barcode/save_barcode_data",
            model="stock.picking",
            res_id=False,
            write_field="move_line_ids",
            write_vals=[
                Command.create(
                    {
                        "product_id": self.product.id,
                        "location_id": location.id,
                        "location_dest_id": self.picking_type.default_location_dest_id.id,
                        "quantity": 1,
                        "picked": True,
                    }
                )
            ],
            draft=draft,
        )
        picking = self._pickings()
        self.assertEqual(len(picking), 1)
        self.assertEqual(data["records"]["stock.picking"][0]["id"], picking.id)
        self.assertNotEqual(picking.name, "/")
        self.assertEqual(picking.move_line_ids.product_id, self.product)

    def test_a_draft_takes_only_the_values_it_is_opened_with(self):
        self.authenticate("admin", "admin")
        draft = self._open()["barcode_draft"]
        draft["values"].update(state="done", note="injected")
        self._call(
            "/stock_barcode/save_barcode_data",
            model="stock.picking",
            res_id=False,
            write_field=False,
            write_vals=[],
            draft=draft,
        )
        picking = self._pickings()
        self.assertEqual(picking.state, "draft")
        self.assertFalse(picking.note)

    def test_a_draft_is_refused_for_a_model_without_drafts(self):
        self.authenticate("admin", "admin")
        body = self._post(
            "/stock_barcode/get_barcode_data",
            model="stock.quant",
            res_id=False,
            draft={"values": {"picking_type_id": self.picking_type.id}},
        )
        self.assertEqual(body["error"]["data"]["name"], "odoo.exceptions.UserError")

    def test_a_location_scan_opens_a_draft_confirmed_on_creation(self):
        self.env.ref("base.user_admin").group_ids += self.env.ref(
            "stock.group_stock_multi_locations"
        )
        self.warehouse.int_type_id.active = True
        self.warehouse.lot_stock_id.barcode = "DRAFT-LOC"
        self.authenticate("admin", "admin")
        result = self._call("/stock_barcode/scan_from_main_menu", barcode="DRAFT-LOC")
        self.assertIn("action", result, result)
        context = result["action"]["context"]
        self.assertTrue(context["barcode_draft"]["confirm"])
        internal = self.env["stock.picking"].search(
            [("picking_type_id", "=", self.warehouse.int_type_id.id)]
        )
        self.assertFalse(internal)


@tagged("post_install", "-at_install")
class TestBarcodeDraftPickingTour(TestBarcodeClientAction):
    def test_barcode_draft_picking(self):
        self.picking_type_out.restrict_scan_source_location = "no"
        self.env["stock.quant"]._update_available_quantity(
            self.product1, self.stock_location, 5
        )
        before = self._last_picking(self.picking_type_out)
        self.start_tour("/odoo/barcode", "test_barcode_draft_picking", login="admin")
        created = self.env["stock.picking"].search(
            [
                ("picking_type_id", "=", self.picking_type_out.id),
                ("id", ">", before.id or 0),
            ]
        )
        self.assertEqual(
            len(created), 1, "the open left without a scan created nothing"
        )
        self.assertEqual(created.move_line_ids.product_id, self.product1)
        self.assertEqual(created.user_id, self.env.ref("base.user_admin"))
