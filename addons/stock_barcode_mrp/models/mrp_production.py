from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    move_raw_line_ids = fields.One2many(
        comodel_name="stock.move.line",
        compute="_compute_move_raw_line_ids",
    )
    move_byproduct_line_ids = fields.One2many(
        comodel_name="stock.move.line",
        compute="_compute_move_byproduct_line_ids",
    )
    is_completed = fields.Boolean(compute="_compute_is_completed")
    backorder_ids = fields.One2many(related="production_group_id.production_ids")

    @api.depends("move_raw_ids")
    def _compute_move_raw_line_ids(self) -> None:
        for order in self:
            order.move_raw_line_ids = order.move_raw_ids.move_line_ids

    @api.depends("move_byproduct_ids")
    def _compute_move_byproduct_line_ids(self) -> None:
        for order in self:
            order.move_byproduct_line_ids = order.move_byproduct_ids.move_line_ids

    @api.depends("qty_produced", "product_qty")
    def _compute_is_completed(self) -> None:
        for order in self:
            order.is_completed = order.qty_produced == order.product_qty

    def action_view_barcode_client_action(self):
        self.check_singleton()
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "stock_barcode_mrp.stock_barcode_mo_client_action"
        )
        context = {"active_id": self.id}
        return dict(action, context=context)

    def set_lot_producing(self) -> tuple:
        action = self.action_generate_serial()
        if action and action["type"] == "ir.actions.act_window":
            return None, action
        return self.trace_producing_ids.read(
            self.trace_producing_ids._get_fields_stock_barcode(), load=False
        ), action

    def _get_fields_stock_barcode(self):
        return [
            "move_raw_line_ids",
            "move_raw_ids",
            "move_byproduct_line_ids",
            "move_byproduct_ids",
            "production_location_id",
            "picking_type_id",
            "location_src_id",
            "location_dest_id",
            "product_id",
            "product_uom_id",
            "product_qty",
            "qty_producing",
            "trace_producing_ids",
            "name",
            "state",
            "picking_type_id",
            "company_id",
            "user_id",
            "production_group_id",
            "backorder_ids",
            "use_create_components_lots",
        ]

    def _get_stock_barcode_data(self):
        self = self.with_context(display_default_code=False)
        move_lines = self.move_raw_line_ids | self.move_byproduct_line_ids
        lots = move_lines.trace_id | self.trace_producing_ids
        owners = move_lines.owner_id
        products = (
            self.product_id | (self.move_raw_ids + self.move_byproduct_ids).product_id
        )
        moves = self.move_raw_ids | self.move_byproduct_ids

        uoms = products.uom_id | move_lines.product_uom_id | products.uom_ids
        if self.env.user.has_group("base.group_uom"):
            uoms |= self.env["uom.uom"].search([])

        source_locations = self.env["stock.location"].search(
            [("id", "child_of", self.location_src_id.ids)]
        )
        destination_locations = self.env["stock.location"].search(
            [("id", "child_of", self.location_dest_id.ids)]
        )
        locations = (
            move_lines.location_id
            | move_lines.location_dest_id
            | source_locations
            | destination_locations
            | self.production_location_id
        )

        packages = self.env["stock.package"]
        package_types = self.env["stock.package.type"]
        if self.env.user.has_group("stock.group_tracking_lot"):
            packages |= move_lines.package_id | move_lines.result_package_id
            packages |= (
                self.env["stock.package"]
                .with_context(pack_locs=destination_locations.ids)
                ._get_usable_packages()
            )
            package_types = package_types.search([])

        data = {
            "records": {
                "mrp.production": self.read(
                    self._get_fields_stock_barcode(), load=False
                ),
                "stock.picking.type": self.picking_type_id.read(
                    self.picking_type_id._get_fields_stock_barcode(), load=False
                ),
                "stock.move": moves.read(moves._get_fields_stock_barcode(), load=False),
                "stock.move.line": move_lines.read(
                    move_lines._get_fields_stock_barcode(), load=False
                ),
                "product.product": products.read(
                    products._get_fields_stock_barcode(), load=False
                ),
                "res.partner": owners.read(
                    owners._get_fields_stock_barcode(), load=False
                ),
                "stock.location": locations.read(
                    locations._get_fields_stock_barcode(), load=False
                ),
                "stock.package.type": package_types.read(
                    package_types._get_fields_stock_barcode(), False
                ),
                "stock.package": packages.read(
                    packages._get_fields_stock_barcode(), load=False
                ),
                "product.trace": lots.read(
                    lots._get_fields_stock_barcode(), load=False
                ),
                "uom.uom": uoms.read(uoms._get_fields_stock_barcode(), load=False),
            },
            "nomenclature_id": self.env.company.sudo().barcodes_config_id.nomenclature_id.id,
            "source_location_ids": source_locations.ids,
            "destination_locations_ids": destination_locations.ids,
        }

        data["config"] = self.picking_type_id._get_barcode_config() if self else {}
        data["line_view_id"] = self.env.ref(
            "stock_barcode_mrp.stock_move_line_product_selector"
        ).id
        data["form_view_id"] = self.env.ref("stock_barcode_mrp.mrp_barcode_form").id
        data["header_view_id"] = self.env.ref(
            "stock_barcode_mrp.mrp_product_selector"
        ).id
        data["scrap_view_id"] = self.env.ref("stock_barcode.scrap_product_selector").id
        data["package_view_id"] = self.env.ref(
            "stock_barcode.stock_quant_barcode_kanban"
        ).id
        return data

    @api.model
    def filter_on_barcode(self, barcode):
        barcode_type = None
        nomenclature = self.env.company.sudo().barcodes_config_id.nomenclature_id
        if nomenclature.is_gs1_nomenclature:
            parsed_results = nomenclature.parse_barcode(barcode)
            if parsed_results:
                for result in parsed_results[::-1]:
                    if result["type"] in ("product", "package"):
                        barcode_type = result["type"]
                        break

        base_domain = [
            ("state", "in", ["confirmed", "progress"]),
            ("reservation_state", "=", "assigned"),
        ]

        active_id = self.env.context.get("active_id")
        additional_context = {
            "search_default_filter_confirmed": 1,
            "search_default_filter_ready": 1,
            "search_default_filter_in_progress": 1,
            "search_default_filter_to_close": 1,
            "search_default_todo": 1,
            "active_id": active_id,
        }
        picking_type = self.env["stock.picking.type"].browse(active_id)
        mo_nums = 0
        if barcode_type == "product" or not barcode_type:
            product = self.env["product.product"].search(
                [("barcode", "=", barcode)], limit=1
            )
            if product:
                mo_nums = self.search_count(
                    base_domain + [("product_id", "=", product.id)]
                )
                if mo_nums:
                    additional_context["search_default_product_id"] = product.id
                else:
                    mo_nums = self.search_count(
                        base_domain + [("move_raw_ids.product_id", "=", product.id)]
                    )
                    additional_context["search_default_move_raw_ids"] = barcode
        if not barcode_type and not mo_nums:
            mo_nums = self.search_count(base_domain + [("name", "=", barcode)])
            additional_context["search_default_name"] = barcode

        _debug.logic(
            "barcode_filter",
            barcode_type=barcode_type or "none",
            matches=mo_nums,
            picking_type=picking_type.id,
        )
        if not mo_nums:
            if barcode_type:
                return {
                    "warning": {
                        "message": self.env._(
                            "No Manufacturing Order ready for this %(barcode_type)s",
                            barcode_type=barcode_type,
                        ),
                    }
                }
            return {
                "warning": {
                    "title": self.env._(
                        "No product or order found for barcode %s", barcode
                    ),
                    "message": self.env._("Scan a product to filter the orders."),
                }
            }

        action = picking_type._prepare_action_by_xml_id(
            "stock_barcode_mrp.mrp_action_kanban"
        )
        action["context"].update(additional_context)
        return {"action": action}

    @api.model
    def _get_new_production_client_action(self) -> dict:
        action = self.env["ir.actions.actions"]._get_action_dict_by_xml_id(
            "stock_barcode_mrp.stock_barcode_mo_client_action"
        )
        action = dict(action, target="fullscreen")
        action["context"] = self.env.context
        return {"action": action}

    def _is_result_return_required(self) -> bool:
        return super()._is_result_return_required() and not self.env.context.get(
            "barcode_trigger", False
        )
