from odoo import api, models
from odoo.api import ValuesType
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import LazyTranslate, html2plaintext, is_html_empty

_debug = DebugLog(__name__)
_lt = LazyTranslate(__name__)


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "stock.barcode.draft.mixin"]
    _barcode_field = "name"
    _barcode_draft_fields = frozenset(
        ("picking_type_id", "location_id", "location_dest_id", "user_id")
    )
    _barcode_client_action = "stock_barcode.stock_barcode_picking_client_action"

    def action_cancel_from_barcode(self) -> dict:
        _debug.lifecycle("barcode_picking_cancel", pickings=self)
        self.check_singleton()
        view = self.env.ref("stock_barcode.stock_barcode_cancel_operation_view")
        return {
            "name": self.env._("Cancel this operation?"),
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "wizard.stock.picking.cancel",
            "views": [(view.id, "form")],
            "view_id": view.id,
            "target": "new",
            "context": dict(self.env.context, default_picking_id=self.id),
        }

    @api.model
    def action_view_new_picking(self):
        context = self.env.context
        if context.get("active_model") == "stock.picking.type":
            picking_type = self.env["stock.picking.type"].browse(
                context.get("active_id")
            )
            if picking_type.exists():
                return self._action_open_barcode_draft(
                    self._prepare_barcode_draft_vals(picking_type)
                )
        return None

    @api.model
    def _check_barcode_draft_values(self, values) -> None:
        if not values.get("picking_type_id"):
            raise UserError(self.env._("A new operation needs an operation type."))

    def action_view_picking_client_action(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            self._barcode_client_action
        )
        context = {"active_id": self.id}
        return dict(action, context=context)

    def action_create_return_picking(self):
        _debug.pipeline("barcode_return_create", pickings=self)
        self.check_singleton()
        return_picking = (
            self.with_context(active_model="stock.picking", active_id=self.id)
            .env["wizard.stock.picking.return"]
            .create({})
        )
        for line in return_picking.product_return_moves:
            line.quantity = line.move_id.quantity
        new_picking = return_picking._create_return()
        return new_picking.action_view_picking_client_action()

    def action_print_barcode(self):
        return self.action_view_label_type()

    def action_print_delivery_slip(self):
        return self.env.ref("stock.action_report_delivery").report_action(self)

    def action_print_packages(self):
        return self.env.ref("stock.action_report_picking_packages").report_action(self)

    def _get_stock_barcode_data(self):
        _debug.perf.count("picking_barcode_data", pickings=self)
        self = self.with_context(display_default_code=False)
        move_lines = self.move_line_ids
        lots = move_lines.trace_id
        partners = move_lines.owner_id | self.partner_id
        products = self.move_ids.product_id | move_lines.product_id

        uoms = (
            products.uom_id
            | move_lines.product_uom_id
            | move_lines.packaging_uom_id
            | products.uom_ids
        )
        if self.env.user.has_group("base.group_uom"):
            uoms |= self.env["uom.uom"].search([])

        product_uoms = products.product_uom_ids

        source_locations = self.env["stock.location"].search(
            [("id", "child_of", self.location_id.ids)]
        )
        destination_locations = self.env["stock.location"].search(
            [("id", "child_of", self.location_dest_id.ids)]
        )
        locations = (
            self.location_id
            | self.location_dest_id
            | move_lines.location_id
            | move_lines.location_dest_id
            | source_locations
            | destination_locations
        )

        packages = self.env["stock.package"]
        package_types = self.env["stock.package.type"]
        if self.env.user.has_group("stock.group_tracking_lot"):
            packages |= move_lines.package_id
            packages |= self.env["stock.package"].search(
                [("id", "parent_of", move_lines.package_id.ids)]
            )
            packages |= self.env["stock.package"].browse(
                move_lines.result_package_id._get_all_package_dest_ids()
            )
            package_locations = destination_locations.filtered(
                lambda location: location.usage != "customer"
            )
            packages |= (
                self.env["stock.package"]
                .with_context(pack_locs=package_locations.ids)
                ._get_usable_packages()
            )
            package_types = package_types.search([])

        data = {
            "records": {
                "stock.picking": self.read(
                    self._get_fields_stock_barcode(), load=False
                ),
                "stock.picking.type": self.picking_type_id.read(
                    self.picking_type_id._get_fields_stock_barcode(), load=False
                ),
                "stock.move": self.move_ids.read(
                    self.move_ids._get_fields_stock_barcode(), load=False
                ),
                "stock.move.line": move_lines.read(
                    move_lines._get_fields_stock_barcode(), load=False
                ),
                "product.product": products.with_context(
                    partner_id=self[:1].partner_id.id
                ).read(products._get_fields_stock_barcode(), load=False),
                "res.partner": partners.read(
                    partners._get_fields_stock_barcode(), load=False
                ),
                "stock.location": locations.read(
                    locations._get_fields_stock_barcode(), load=False
                ),
                "stock.package.type": package_types.read(
                    package_types._get_fields_stock_barcode(), load=False
                ),
                "stock.package": packages.read(
                    packages._get_fields_stock_barcode(), load=False
                ),
                "product.trace": lots.read(
                    lots._get_fields_stock_barcode(), load=False
                ),
                "uom.uom": uoms.read(uoms._get_fields_stock_barcode(), load=False),
                "product.uom": product_uoms.read(
                    product_uoms._get_fields_stock_barcode(), load=False
                ),
            },
            "nomenclature_id": self.env.company.sudo().barcodes_config_id.nomenclature_id.id,
            "source_location_ids": source_locations.ids,
            "destination_locations_ids": destination_locations.ids,
        }
        for picking in data["records"]["stock.picking"]:
            picking["note"] = (
                False
                if is_html_empty(picking["note"])
                else html2plaintext(picking["note"])
            )

        data["config"] = self.picking_type_id._get_barcode_config()
        if self._is_backorder_ignore_required():
            data["config"]["create_backorder"] = "never"
        view_id = self.env["ir.model.data"]._xmlid_to_res_id
        data["line_view_id"] = view_id(
            "stock_barcode.stock_move_line_product_selector", raise_if_not_found=True
        )
        data["form_view_id"] = view_id(
            "stock_barcode.stock_picking_barcode", raise_if_not_found=True
        )
        data["scrap_view_id"] = view_id(
            "stock_barcode.scrap_product_selector", raise_if_not_found=True
        )
        data["package_view_id"] = view_id(
            "stock_barcode.stock_quant_barcode_kanban", raise_if_not_found=True
        )
        return data

    @api.model
    def _prepare_barcode_draft_vals(self, picking_type) -> ValuesType:
        location_dest_id, location_id = (
            picking_type.warehouse_id._get_partner_locations()
        )
        if picking_type.default_location_src_id:
            location_id = picking_type.default_location_src_id
        if picking_type.default_location_dest_id:
            location_dest_id = picking_type.default_location_dest_id
        return {
            "user_id": False,
            "picking_type_id": picking_type.id,
            "location_id": location_id.id,
            "location_dest_id": location_dest_id.id,
        }

    def _get_fields_stock_barcode(self):
        return [
            "company_id",
            "location_dest_id",
            "location_id",
            "move_ids",
            "move_line_ids",
            "name",
            "note",
            "partner_id",
            "picking_type_code",
            "picking_type_entire_packs",
            "picking_type_id",
            "picking_warning_text",
            "return_id",
            "signature",
            "state",
            "use_create_lots",
            "use_existing_lots",
            "user_id",
        ]

    @api.model
    def filter_on_barcode(self, barcode):
        _debug.pipeline("picking_filter_on_barcode", pickings=self, barcode=barcode)
        barcode_type = None
        nomenclature = self.env.company.sudo().barcodes_config_id.nomenclature_id
        if nomenclature.is_gs1_nomenclature:
            parsed_results = nomenclature.parse_barcode(barcode)
            if parsed_results:
                for result in parsed_results[::-1]:
                    if result["type"] in ("product", "package", "lot"):
                        barcode_type = result["type"]
                        break

        active_id = self.env.context.get("active_id")
        picking_type = self.env["stock.picking.type"].browse(active_id)
        base_domain = [
            ("picking_type_id", "=", picking_type.id),
            ("state", "not in", ["cancel", "done", "draft"]),
        ]
        is_lot_enabled = self.env.user.has_group("stock.group_production_lot")
        is_pack_enabled = self.env.user.has_group("stock.group_tracking_lot")
        is_uom_enabled = self.env.user.has_group("base.group_uom")

        picking_nums = 0
        additional_context = {
            "active_id": active_id,
            "active_model": "stock.picking.type",
        }
        if barcode_type == "product" or not barcode_type:
            product = self.env["product.product"].search(
                [("barcode", "=", barcode)], limit=1
            )
            if (
                not product and is_uom_enabled
            ):
                product_packaging = self.env["product.uom"].search(
                    [("barcode", "=", barcode)], limit=1
                )
                product = (
                    product_packaging.product_id
                )
            if product:
                picking_nums = self.search_count(
                    base_domain + [("product_id", "=", product.id)]
                )
                additional_context["search_default_product_id"] = product.id
        if is_pack_enabled and (
            barcode_type == "package" or (not barcode_type and not picking_nums)
        ):
            package = self.env["stock.package"].search(
                [("name", "=", barcode)], limit=1
            )
            if package:
                pack_domain = [
                    "|",
                    ("move_line_ids.package_id", "=", package.id),
                    ("move_line_ids.result_package_id", "=", package.id),
                ]
                picking_nums = self.search_count(base_domain + pack_domain)
                additional_context["search_default_move_line_ids"] = barcode
        if is_lot_enabled and (
            barcode_type == "lot" or (not barcode_type and not picking_nums)
        ):
            lot = self.env["product.trace"].search(
                [
                    ("name", "=", barcode),
                    "|",
                    ("company_id", "=", False),
                    ("company_id", "=", picking_type.company_id.id),
                ],
                limit=1,
            )
            if lot:
                lot_domain = [("move_line_ids.trace_id", "=", lot.id)]
                picking_nums = self.search_count(base_domain + lot_domain)
                additional_context["search_default_trace_id"] = lot.id
        if (
            not barcode_type and not picking_nums
        ):
            picking_nums = self.search_count(base_domain + [("name", "=", barcode)])
            additional_context["search_default_name"] = barcode

        if not picking_nums:
            if barcode_type:
                message = self.env._(self._BARCODE_TYPE_NOT_READY[barcode_type])
                return {
                    "warning": {
                        "message": message % {"picking_type": picking_type.name},
                    }
                }
            title, message = self._get_barcode_filter_warning(
                is_lot_enabled, is_pack_enabled, is_uom_enabled, barcode
            )
            return {
                "warning": {
                    "title": title,
                    "message": message,
                }
            }

        action = picking_type._prepare_action_by_xml_id(
            "stock_barcode.stock_picking_action_kanban"
        )
        action["context"].update(additional_context)
        return {"action": action}

    _BARCODE_TYPE_NOT_READY = {
        "product": _lt("No %(picking_type)s ready for this product"),
        "package": _lt("No %(picking_type)s ready for this package"),
        "lot": _lt("No %(picking_type)s ready for this lot"),
    }

    _BARCODE_FILTER_WARNINGS = {
        (True, True, True): (
            lambda barcode: _lt(
                "No product, lot, packaging, or package found for barcode %s", barcode
            ),
            _lt(
                "Scan a product, a lot, a packaging, or a package to filter the transfers."
            ),
        ),
        (True, True, False): (
            lambda barcode: _lt(
                "No product, lot, or package found for barcode %s", barcode
            ),
            _lt("Scan a product, a lot, or a package to filter the transfers."),
        ),
        (True, False, True): (
            lambda barcode: _lt(
                "No product, lot, or packaging found for barcode %s", barcode
            ),
            _lt("Scan a product, a lot, or a packaging to filter the transfers."),
        ),
        (True, False, False): (
            lambda barcode: _lt("No product or lot found for barcode %s", barcode),
            _lt("Scan a product or a lot to filter the transfers."),
        ),
        (False, True, True): (
            lambda barcode: _lt(
                "No product, package, or packaging found for barcode %s", barcode
            ),
            _lt("Scan a product, a package, or a packaging to filter the transfers."),
        ),
        (False, True, False): (
            lambda barcode: _lt("No product or package found for barcode %s", barcode),
            _lt("Scan a product or a package to filter the transfers."),
        ),
        (False, False, True): (
            lambda barcode: _lt(
                "No product or packaging found for barcode %s", barcode
            ),
            _lt("Scan a product or a packaging to filter the transfers."),
        ),
        (False, False, False): (
            lambda barcode: _lt("No product found for barcode %s", barcode),
            _lt("Scan a product to filter the transfers."),
        ),
    }

    def _get_barcode_filter_warning(
        self, is_lot_enabled, is_pack_enabled, is_uom_enabled, barcode
    ) -> tuple:
        _debug.logic("barcode_filter_warning", pickings=self)
        title, message = self._BARCODE_FILTER_WARNINGS[
            (bool(is_lot_enabled), bool(is_pack_enabled), bool(is_uom_enabled))
        ]
        return self.env._(title(barcode)), self.env._(message)
