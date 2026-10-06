from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    check_id = fields.One2many(
        comodel_name="quality.check",
        inverse_name="move_id",
    )
    note = fields.Html(
        related="check_id.note",
        string="Note",
    )
    worksheet_document = fields.Binary(
        string="Worksheet Image/PDF",
        compute="_compute_worksheet_document",
    )
    product_barcode = fields.Char(related="product_id.barcode")
    move_line_ids_picked = fields.One2many(
        comodel_name="stock.move.line",
        inverse_name="move_id",
        domain=[("picked", "=", True)],
    )
    picking_type_prefill_shop_floor_lots = fields.Boolean(
        related="picking_type_id.prefill_shop_floor_lots"
    )

    @api.depends("check_id.worksheet_document")
    def _compute_worksheet_document(self) -> None:
        for record in self:
            if record.check_id:
                record.worksheet_document = record.check_id.worksheet_document
            else:
                record.worksheet_document = None

    @api.depends("workorder_id")
    def _compute_manual_consumption(self) -> None:
        super()._compute_manual_consumption()
        for move in self:
            if (
                move.product_id in move.workorder_id.check_ids.component_id
                and move.product_id
                not in move.raw_material_production_id.workorder_ids.check_ids.component_id
            ):
                move.manual_consumption = True

    def _is_qty_producing_bypass_required(self) -> bool:
        production = self.raw_material_production_id or self.production_id
        if production and (
            (self.product_id in production.workorder_ids.quality_point_ids.component_id)
            or self.operation_id
        ):
            return True
        return super()._is_qty_producing_bypass_required()

    def _action_assign(self):
        res = super()._action_assign()
        # Only refresh the checks tied to the moves this call actually
        # (re)assigned, not every check in the whole production(s) behind
        # `self` -- those checks' lot defaults haven't changed.
        # Reservation runs for whoever confirms the order -- a purchase or sales
        # user with no quality access -- while the checks belong to the shop floor.
        checks = (
            self.env["quality.check"]
            .sudo()
            .search(
                [
                    ("move_id", "in", self.ids),
                    (
                        "test_type",
                        "in",
                        ("register_consumed_materials", "register_byproducts"),
                    ),
                ]
            )
        )
        for check in checks:
            check.write(check.workorder_id._prepare_check_vals_from_move(check.move_id))
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_quality_check(self) -> None:
        self.env["quality.check"].search([("move_id", "in", self.ids)]).unlink()

    def action_add_from_catalog_raw(self):
        mo = self.env["mrp.production"].browse(self.env.context.get("order_id"))
        return mo.with_context(
            child_field="move_raw_ids",
            from_shop_floor=self.env.context.get("from_shop_floor"),
        ).action_add_from_catalog()

    def action_pass(self, keep_hidden_lines=False) -> bool:
        _debug.pipeline(
            "shopfloor_move_passed",
            moves=self,
            checks=len(self.check_id),
            keep_hidden=keep_hidden_lines,
        )
        if not keep_hidden_lines:
            for record in self:
                if (
                    record.has_tracking != "none"
                    and not record.picking_type_id.prefill_shop_floor_lots
                ):
                    # Remove any reserved smls that are hidden
                    record.move_line_ids.filtered(lambda ml: not ml.picked).unlink()
        for check in self.check_id:
            check.action_next()
        if not self.check_id:
            self.picked = True
        return True

    def action_undo(self) -> None:
        _debug.lifecycle("shopfloor_move_undone", moves=self, checks=len(self.check_id))
        if self.check_id:
            self.check_id.write({"quality_state": "none"})
        self.picked = False
        self.quantity = self.product_uom_qty

    def get_or_create_quant_id_from_barcode(self, barcode: str) -> int | None:
        self.check_singleton()
        if self.product_id.tracking == "none":
            return None
        trace_id = self.env["product.trace"].search(
            [("name", "=", barcode), ("product_id", "=", self.product_id.id)], limit=1
        )
        if not trace_id:
            _debug.lifecycle(
                "shopfloor_lot_created", move=self.id, product=self.product_id.id
            )
            trace_id = (
                self.env["product.trace"]
                .with_context(active_mo_id=self.raw_material_production_id.id)
                .create([{"name": barcode, "product_id": self.product_id.id}])
            )
            return (
                self.env["stock.quant"]
                .create(
                    [
                        {
                            "trace_id": trace_id.id,
                            "product_id": self.product_id.id,
                            "location_id": (
                                self.raw_material_production_id.location_src_id
                                or self.warehouse_id.lot_stock_id
                            ).id,
                        }
                    ]
                )
                .id
            )
        # Same quants the "Add line" picker lists: on hand in the MO's source.
        return (
            self.env["stock.quant"]
            .search(
                [
                    ("trace_id", "=", trace_id.id),
                    ("product_id", "=", self.product_id.id),
                    (
                        "location_id",
                        "child_of",
                        self.raw_material_production_id.location_src_id.id,
                    ),
                    ("on_hand", "=", True),
                    ("quantity", ">", 0.0),
                ],
                limit=1,
            )
            .id
        ) or None

    def _get_visible_quantity(self):
        self.check_singleton()
        if self.env.context.get("hide_unpicked"):
            return sum(
                sml.product_uom_id._get_quantity_report(
                    sml.quantity, self.product_uom_id, rounding_method="HALF-UP"
                )
                for sml in self.move_line_ids_picked
            )
        return super()._get_visible_quantity()

    def _add_from_quant(self, quant) -> None:
        hide_unpicked = (
            self.product_id.tracking != "none"
            and not self.picking_type_prefill_shop_floor_lots
        )
        if hide_unpicked:
            move_line = next(
                (
                    sml
                    for sml in self.move_line_ids
                    if sml._is_taken_from_quant(quant) and not sml.picked
                ),
                False,
            )
            if move_line:  # Quant already has hidden sml -> make visible
                _debug.logic(
                    "quant_added",
                    move=self.id,
                    by="unhid_existing_line",
                    quant=quant.id,
                )
                move_line.picked = True
                return
        remaining_qty = self.product_qty - sum(
            sml.quantity_product_uom
            for sml in self.move_line_ids
            if not hide_unpicked or sml.picked
        )
        if (
            min(remaining_qty, quant.available_quantity) > 0
            and self.product_id.tracking != "serial"
        ):
            qty_to_take = min(remaining_qty, quant.available_quantity)
        else:
            qty_to_take = 1
        move_line = next(
            (sml for sml in self.move_line_ids if sml._is_taken_from_quant(quant)),
            False,
        )
        if (
            move_line
        ):  # Quant already has visible sml -> increase existing sml's quantity
            _debug.logic(
                "quant_added", move=self.id, by="increased_line", qty=qty_to_take
            )
            move_line.quantity += self.product_id.uom_id._get_quantity_in_unit(
                qty_to_take, self.product_uom_id
            )
        else:  # No sml exists for quant -> make new sml
            _debug.logic("quant_added", move=self.id, by="new_line", qty=qty_to_take)
            move_line_vals = self._prepare_move_line_vals(
                quantity=qty_to_take, reserved_quant=quant
            )
            self.env["stock.move.line"].create([{**move_line_vals, "picked": True}])

    def action_add_from_quant(self, quant_id) -> None:
        self._add_from_quant(self.env["stock.quant"].browse(quant_id))

        if (
            self.product_id.tracking != "none"
            and not self.picking_type_prefill_shop_floor_lots
        ):
            self.move_line_ids.filtered(lambda ml: not ml.picked).unlink()

        if self.check_id:
            self.check_id.action_next()


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def _is_taken_from_quant(self, quant) -> bool:
        self.check_singleton()
        fields_to_match = (
            "location_id",
            "product_id",
            "owner_id",
            "package_id",
            "trace_id",
        )
        return all(self[field] == quant[field] for field in fields_to_match)
