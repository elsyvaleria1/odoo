from odoo import Command
from odoo.libs.json import dumps as json_dumps
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestStockBarcodeController(HttpCase):
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

    def _call_error(self, route, **params):
        body = self._post(route, **params)
        self.assertIn("error", body, body.get("result"))
        return body["error"]["data"]

    def _scan_from_main_menu(self, barcode):
        return self._call("/stock_barcode/scan_from_main_menu", barcode=barcode)

    def test_search_by_barcode_with_multiple_companies(self):
        company_a = self.env.company
        company_b = self.env["res.company"].create({"name": "Test Company"})
        self.env.ref("base.user_admin").company_ids = [Command.link(company_b.id)]

        products = [
            {"name": "A1", "barcode": "abc1", "company_id": False},
            {"name": "A2", "barcode": "abc2", "company_id": False},
            {"name": "A3", "barcode": "abc3", "company_id": company_a.id},
            {"name": "A4", "barcode": "abc3", "company_id": company_b.id},
        ]

        for product in products:
            self.env["product.product"].create(product)

        expected_responses = {
            company_a: [
                ("abc1", "A1"),
                ("abc2", "A2"),
                ("abc3", "A3"),
            ],
            company_b: [
                ("abc1", "A1"),
                ("abc2", "A2"),
                ("abc3", "A4"),
            ],
        }

        self.authenticate("admin", "admin")
        for company, responses in expected_responses.items():
            for barcode, expected_display_name in responses:
                self.env.ref("base.user_admin").company_id = company
                result = self._call(
                    "/stock_barcode/get_specific_barcode_data",
                    barcode=barcode,
                    domains_by_model={
                        "all": [["company_id", "in", [False, company.id]]]
                    },
                )
                self.assertEqual(
                    [
                        (product["barcode"], product["display_name"])
                        for product in result["records"]["product.product"]
                    ],
                    [(barcode, expected_display_name)],
                    company.name,
                )

    def test_search_barcode_for_package_type(self):
        package_type = self.env["stock.package.type"].create(
            {"name": "Barcoded box", "barcode": "00000012345678"}
        )
        self.authenticate("admin", "admin")
        result = self._call(
            "/stock_barcode/get_specific_barcode_data",
            barcodes_by_model={"stock.package.type": ["00000012345678"]},
            domains_by_model={},
        )
        self.assertEqual(
            [record["id"] for record in result["records"]["stock.package.type"]],
            [package_type.id],
        )

    def test_barcode_with_uri_without_gs1_nomenclature(self):
        product = self.env["product.product"].create(
            {"name": "SGTIN product", "barcode": "00614141386567"}
        )
        self.authenticate("admin", "admin")
        result = self._scan_from_main_menu("urn:epc:tag:sgtin-96 : 3.0614141.038656.0")
        self.assertEqual(
            result.get("action", {}).get("res_model"), "stock.quant", result
        )
        self.assertIn(["product_id", "=", product.id], result["action"]["domain"])

    def test_barcode_with_uri_with_gs1_nomenclature(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        product = self.env["product.product"].create(
            {"name": "SGTIN product", "barcode": "00614141386567"}
        )
        self.authenticate("admin", "admin")
        result = self._scan_from_main_menu("urn:epc:tag:sgtin-96 : 3.0614141.038656.0")
        self.assertEqual(
            result.get("action", {}).get("res_model"), "stock.quant", result
        )
        self.assertIn(["product_id", "=", product.id], result["action"]["domain"])

    def test_main_menu_returns_product_location_action(self):
        product = self.env["product.product"].create(
            {
                "name": "Test Product",
                "barcode": "15099590483921",
            }
        )
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        self.authenticate("admin", "admin")
        result = self._scan_from_main_menu("15099590483921")
        self.assertEqual(result["action"]["res_model"], "stock.quant")
        self.assertIn(["product_id", "=", product.id], result["action"]["domain"])

    def test_play_sound_reads_the_mute_parameter_as_a_boolean(self):
        self.authenticate("admin", "admin")
        params = self.env["ir.config_parameter"].sudo()
        for value, expected in ((False, True), ("False", True), ("True", False)):
            params.set_param("stock_barcode.mute_sound_notifications", value)
            result = self._call("/stock_barcode/get_main_menu_data")
            self.assertIs(result["play_sound"], expected, value)

    def test_specific_barcode_data_refuses_a_model_it_does_not_scan(self):
        self.authenticate("admin", "admin")
        for model in ("res.users", "no.such.model"):
            error = self._call_error(
                "/stock_barcode/get_specific_barcode_data",
                barcodes_by_model={model: ["admin"]},
            )
            self.assertEqual(error["name"], "odoo.exceptions.UserError", model)

    def test_demo_message_route_refuses_a_non_stock_user(self):
        self.env["res.users"].create(
            {"name": "No stock", "login": "nostock", "password": "nostock-pass"}
        )
        self.authenticate("nostock", "nostock-pass")
        error = self._call_error("/stock_barcode/rid_of_message_demo_barcodes")
        self.assertEqual(error["name"], "werkzeug.exceptions.NotFound")

    def test_an_inventory_user_dismisses_the_demo_message(self):
        new_test_user(self.env, login="demo_dismisser", groups="stock.group_stock_user")
        action = self.env.ref("stock_barcode.stock_barcode_action_main_menu")
        action.params = {"message_demo_barcodes": True}
        self.authenticate("demo_dismisser", "demo_dismisser")
        self._call("/stock_barcode/rid_of_message_demo_barcodes")
        self.env.invalidate_all()
        self.assertEqual(action.params, {"message_demo_barcodes": False})

    def _print_barcode_sheet(self, login, barcode_type):
        self.env["stock.picking.type"].with_context(active_test=False).search([]).write(
            {"barcode": False}
        )
        self.authenticate(login, login)
        return self.url_open(
            f"/stock_barcode/print_inventory_commands?barcode_type={barcode_type}"
        )

    def test_an_inventory_user_prints_the_barcode_sheet(self):
        new_test_user(self.env, login="sheet_printer", groups="stock.group_stock_user")
        response = self._print_barcode_sheet(
            "sheet_printer", "barcode_commands_and_operation_types"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")

    def test_a_non_inventory_user_cannot_print_the_barcode_sheet(self):
        new_test_user(self.env, login="sheet_outsider", groups="base.group_user")
        response = self._print_barcode_sheet(
            "sheet_outsider", "barcode_commands_and_operation_types"
        )
        self.assertEqual(response.status_code, 404)

    def test_saving_answers_in_the_company_the_switcher_selected(self):
        company_b = self.env["res.company"].create({"name": "Barcode company B"})
        admin = self.env.ref("base.user_admin")
        admin.company_ids = [Command.link(company_b.id)]
        nomenclature_b = self.env["barcode.nomenclature"].create(
            {"name": "Company B nomenclature"}
        )
        company_b.barcodes_config_id.nomenclature_id = nomenclature_b
        location_b = (
            self.env["stock.warehouse"]
            .search([("company_id", "=", company_b.id)], limit=1)
            .lot_stock_id
        )
        product = self.env["product.product"].create(
            {"name": "Company B product", "is_storable": True}
        )
        self.authenticate("admin", "admin")
        self.opener.cookies["cids"] = str(company_b.id)
        result = self._call(
            "/stock_barcode/save_barcode_data",
            model="stock.quant",
            res_id=False,
            write_field=False,
            write_vals=[
                Command.create(
                    {
                        "product_id": product.id,
                        "location_id": location_b.id,
                        "inventory_quantity": 1,
                        "inventory_quantity_set": True,
                    }
                )
            ],
        )
        self.assertEqual(result["nomenclature_id"], nomenclature_b.id)

    def test_main_menu_reads_the_selected_companys_nomenclature(self):
        company_b = self.env["res.company"].create({"name": "GS1 company"})
        self.env.ref("base.user_admin").company_ids = [Command.link(company_b.id)]
        company_b.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        product = self.env["product.product"].create(
            {"name": "GS1 product", "barcode": "36939282410106"}
        )
        self.authenticate("admin", "admin")
        self.opener.cookies["cids"] = str(company_b.id)
        result = self._scan_from_main_menu("0136939282410106")
        self.assertEqual(
            result.get("action", {}).get("res_model"), "stock.quant", result
        )
        self.assertIn(["product_id", "=", product.id], result["action"]["domain"])

    def test_main_menu_finds_the_product_of_a_weight_embedded_barcode(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes.default_barcode_nomenclature"
        )
        product = self.env["product.product"].create(
            {"name": "Weighed product", "barcode": "2155555000000"}
        )
        self.authenticate("admin", "admin")
        result = self._scan_from_main_menu("2155555050005")
        self.assertEqual(
            result.get("action", {}).get("res_model"), "stock.quant", result
        )
        self.assertIn(["product_id", "=", product.id], result["action"]["domain"])

    def test_specific_barcode_data_names_the_products_it_sent_every_quant_of(self):
        self.env.company.barcodes_config_id.nomenclature_id = self.env.ref(
            "barcodes_gs1_nomenclature.default_gs1_nomenclature"
        )
        warehouse = self.env["stock.warehouse"].search(
            [("company_id", "=", self.env.company.id)], limit=1
        )
        product, packaged = self.env["product.product"].create(
            [
                {"name": "Counted", "barcode": "2300001000084", "is_storable": True},
                {"name": "Packaged", "barcode": "5468123001239", "is_storable": True},
            ]
        )
        pack = self.env["uom.uom"].create(
            {
                "name": "Pack of 3",
                "relative_factor": 3,
                "relative_uom_id": self.env.ref("base.product_uom_unit").id,
            }
        )
        self.env["product.uom"].create(
            {"barcode": "PACK-3", "uom_id": pack.id, "product_id": packaged.id}
        )
        for record in (product, packaged):
            self.env["stock.quant"]._update_available_quantity(
                record, warehouse.lot_stock_id, 4
            )
        self.authenticate("admin", "admin")
        search = {"product.product": ["02300001000084"], "product.uom": ["PACK-3"]}
        result = self._call(
            "/stock_barcode/get_specific_barcode_data",
            barcodes_by_model=search,
            fetch_quants=True,
        )
        self.assertEqual(
            {record["id"] for record in result["records"]["product.product"]},
            {product.id, packaged.id},
        )
        self.assertEqual(
            result["products_with_all_quants"],
            sorted((product | packaged).ids),
            "every product the answer carries comes with all its quants",
        )
        self.assertEqual(
            {quant["product_id"] for quant in result["records"]["stock.quant"]},
            {product.id, packaged.id},
        )
        result = self._call(
            "/stock_barcode/get_specific_barcode_data", barcodes_by_model=search
        )
        self.assertEqual(result["products_with_all_quants"], [])

    def test_get_quants_states_the_products_it_completes(self):
        product = self.env["product.product"].create(
            {"name": "No stock yet", "is_storable": True}
        )
        self.authenticate("admin", "admin")
        result = self._call("/stock_barcode/get_quants", product_ids=[product.id])
        self.assertEqual(result["products_with_all_quants"], [product.id])
        self.assertEqual(result["records"]["stock.quant"], [])
