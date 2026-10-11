from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    product_barcode = fields.Char(related="product_id.barcode")
    formatted_product_barcode = fields.Char(
        compute="_compute_formatted_product_barcode"
    )
    dummy_id = fields.Char(
        compute="_compute_dummy_id",
        inverse="_inverse_dummy_id",
    )
    parent_location_id = fields.Many2one(
        comodel_name="stock.location",
        compute="_compute_parent_location_id",
    )
    parent_location_dest_id = fields.Many2one(
        comodel_name="stock.location",
        compute="_compute_parent_location_id",
    )
    product_stock_quant_ids = fields.One2many(
        comodel_name="stock.quant",
        compute="_compute_product_stock_quant_ids",
    )
    lot_properties = fields.Properties(
        related="trace_id.lot_properties",
        definition="product_id.lot_properties_definition",
        readonly=True,
    )
    hide_lot_name = fields.Boolean(compute="_compute_hide_lot_name")
    hide_lot = fields.Boolean(compute="_compute_hide_lot_name")
    image_1920 = fields.Image(related="product_id.image_1920")
    product_reference_code = fields.Char(
        related="product_id.code",
        string="Product Reference Code",
    )
    qty_done = fields.Float(
        digits="Product Unit",
        compute="_compute_qty_done",
        inverse="_inverse_qty_done",
    )
    packaging_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        related="move_id.packaging_uom_id",
        string="Packaging Unit of Measure",
    )
    quantity_packaging_uom = fields.Float(
        related="move_id.quantity_packaging_uom",
        string="Packaging Quantity",
    )
    outermost_result_package_id = fields.Many2one(
        comodel_name="stock.package",
        compute="_compute_outermost_result_package_id",
        inverse="_inverse_outermost_result_package_id",
    )

    @api.depends("result_package_id")
    def _compute_outermost_result_package_id(self) -> None:
        for line in self:
            outermost_package = line.result_package_id.outermost_package_id
            line.outermost_result_package_id = (
                outermost_package
                if outermost_package != line.result_package_id
                else False
            )

    @api.depends(
        "tracking",
        "picking_type_use_existing_lots",
        "picking_type_use_create_lots",
        "lot_name",
    )
    def _compute_hide_lot_name(self) -> None:
        for line in self:
            if line.tracking not in ("lot", "serial"):
                line.hide_lot_name = True
                line.hide_lot = True
                continue
            line.hide_lot_name = not line.picking_type_use_create_lots or (
                line.picking_type_use_existing_lots and not line.lot_name
            )
            line.hide_lot = not line.picking_type_use_existing_lots or (
                line.picking_type_use_create_lots and line.lot_name
            )

    @api.depends("picking_id.location_id", "picking_id.location_dest_id")
    def _compute_parent_location_id(self) -> None:
        for line in self:
            line.parent_location_id = line.picking_id.location_id
            line.parent_location_dest_id = line.picking_id.location_dest_id

    @api.depends("product_id", "parent_location_id")
    def _compute_product_stock_quant_ids(self) -> None:
        _debug.perf.count("barcode_line_quants_compute", lines=self)
        domain = [
            ("product_id", "in", self.product_id.ids),
            ("company_id", "in", self.env.companies.ids),
            ("location_id.usage", "=", "internal"),
            ("quantity", ">", 0),
            ("location_id", "child_of", self.parent_location_id.ids),
        ]
        quants_by_product = dict(
            self.env["stock.quant"]._read_group(
                domain, groupby=["product_id"], aggregates=["id:recordset"]
            )
        )
        no_quant = self.env["stock.quant"]
        for line in self:
            prefix = line.parent_location_id.parent_path
            line.product_stock_quant_ids = (
                quants_by_product.get(line.product_id, no_quant).filtered(
                    lambda quant, prefix=prefix: (
                        quant.location_id.parent_path.startswith(prefix)
                    )
                )
                if prefix
                else no_quant
            )

    def _compute_dummy_id(self) -> None:
        self.dummy_id = ""

    @api.depends("picked", "quantity")
    def _compute_qty_done(self) -> None:
        for line in self:
            line.qty_done = line.quantity if line.picked else 0

    @api.depends("product_barcode")
    def _compute_formatted_product_barcode(self) -> None:
        for line in self:
            line.formatted_product_barcode = (
                f"[{line.product_barcode}]"
                if line.product_barcode
                else self.env._("No Barcode")
            )

    def _inverse_dummy_id(self):
        pass

    def _inverse_outermost_result_package_id(self) -> None:
        def get_before_outermost(package):
            if package.package_dest_id.package_dest_id:
                return get_before_outermost(package.package_dest_id)
            return package

        _debug.lifecycle("barcode_result_package_set", lines=self)
        for line in self:
            if not line.result_package_id:
                if line.outermost_result_package_id:
                    line.action_put_in_pack(
                        package_id=line.outermost_result_package_id.id
                    )
                continue
            package = get_before_outermost(line.result_package_id)
            package.package_dest_id = False
            if line.outermost_result_package_id:
                package.action_put_in_pack(
                    package_id=line.outermost_result_package_id.id
                )

    def _inverse_qty_done(self) -> None:
        _debug.lifecycle("barcode_qty_done_set", lines=self)
        for line in self.with_context({"preserve_state": True}):
            qty_done = line.qty_done
            line.quantity = qty_done
            if qty_done:
                line.picked = True

    @api.model_create_multi
    def create(self, vals_list):
        _debug.lifecycle("barcode_line_create", count=len(vals_list))
        model = self
        carried_qty_done = False
        for vals in vals_list:
            if "qty_done" in vals:
                qty_done = vals.pop("qty_done")
                vals["quantity"] = qty_done
                vals["picked"] = qty_done > 0
                carried_qty_done = True
        if carried_qty_done and "default_qty_done" in self.env.context:
            context = dict(self.env.context)
            del context["default_qty_done"]
            model = self.with_env(self.env(context=context))
        return super(StockMoveLine, model).create(vals_list)

    def _get_fields_stock_barcode(self):
        return [
            "product_id",
            "product_category_name",
            "location_id",
            "location_dest_id",
            "move_id",
            "qty_done",
            "quantity",
            "display_name",
            "product_uom_id",
            "product_barcode",
            "owner_id",
            "trace_id",
            "lot_name",
            "package_id",
            "result_package_id",
            "dummy_id",
            "picked",
            "outermost_result_package_id",
            "packaging_uom_id",
            "quantity_packaging_uom",
            "description_picking",
            "is_entire_pack",
        ]

    def _action_open_choose_destination(self):
        _debug.pipeline("barcode_choose_destination", lines=self)
        res = super()._action_open_choose_destination()
        from_barcode = self.env.context.get("barcode_view")
        if res and from_barcode:
            res["context"] = {**res.get("context", {}), "barcode_view": True}
        return res

    def _is_put_in_pack_wizard_required(
        self, package_id, package_type_id, package_name, from_package_wizard
    ) -> bool:
        _debug.logic("barcode_put_in_pack_required", lines=self)
        if self.env.context.get("barcode_view"):
            return False
        return super()._is_put_in_pack_wizard_required(
            package_id, package_type_id, package_name, from_package_wizard
        )
