from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import float_compare
from odoo.tools.misc import format_date, unique

MAP_REPAIR_TO_PICKING_LOCATIONS = {
    "location_id": "default_location_src_id",
    "location_dest_id": "default_location_dest_id",
    "parts_location_id": "default_remove_location_dest_id",
    "recycle_location_id": "default_recycle_location_dest_id",
}


_debug = DebugLog(__name__)


class RepairOrder(models.Model):

    _name = "repair.order"
    _description = "Repair Order"
    _inherit = [
        "mixin.mail.thread",
        "mixin.mail.activity",
        "mixin.product.catalog",
        "mixin.date.category",
    ]
    _order = "priority desc, create_date desc"
    _date_category_field = "schedule_date"
    _check_company_auto = True

    name = fields.Char(
        string="Repair Reference",
        default="New",
        index="trigram",
        copy=False,
        readonly=True,
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        readonly=True,
        required=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "New"),
            ("confirmed", "Confirmed"),
            ("under_repair", "Under Repair"),
            ("done", "Repaired"),
            ("cancel", "Cancelled"),
        ],
        string="Status",
        default="draft",
        index=True,
        copy=False,
        readonly=True,
        tracking=True,
        help="* The 'New' status is used when a user is encoding a new and unconfirmed repair order.\n"
        "* The 'Confirmed' status is used when a user confirms the repair order.\n"
        "* The 'Under Repair' status is used when the repair is ongoing.\n"
        "* The 'Repaired' status is set when repairing is completed.\n"
        "* The 'Cancelled' status is used when user cancel repair order.",
    )
    priority = fields.Selection(
        selection=[("0", "Normal"), ("1", "Urgent")],
        default="0",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        compute="_compute_partner_id",
        change_default=True,
        store=True,
        index=True,
        readonly=False,
        check_company=True,
        help="Choose partner for whom the order will be invoiced and delivered. You can find a partner by its Name, TIN, Email or Internal Reference.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        default=lambda self: self.env.user,
        check_company=True,
    )

    internal_notes = fields.Html()
    tag_ids = fields.Many2many(
        comodel_name="repair.tags",
        string="Tags",
    )
    under_warranty = fields.Boolean(
        help="If ticked, the sales price will be set to 0 for all products transferred from the repair order."
    )
    schedule_date = fields.Datetime(
        string="Scheduled Date",
        default=fields.Datetime.now,
        index=True,
        copy=False,
        required=True,
    )
    repair_properties = fields.Properties(
        definition="picking_type_id.repair_properties_definition",
        string="Properties",
        copy=True,
    )

    move_id = fields.Many2one(
        comodel_name="stock.move",
        string="Inventory Move",
        copy=False,
        readonly=True,
        check_company=True,
        tracking=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product to Repair",
        domain="[('type', '=', 'consu'), '|', ('company_id', '=', company_id), ('company_id', '=', False), '|', ('id', 'in', picking_product_ids), ('id', '=?', picking_product_id)]",
        check_company=True,
    )
    product_qty = fields.Float(
        string="Product Quantity",
        digits="Product Unit",
        compute="_compute_product_qty",
        store=True,
        readonly=False,
    )
    allowed_uom_ids = fields.Many2many(
        comodel_name="uom.uom",
        compute="_compute_allowed_uom_ids",
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit",
        compute="_compute_product_uom_id",
        precompute=True,
        store=True,
        readonly=False,
        domain="[('id', 'in', allowed_uom_ids)]",
    )
    trace_id = fields.Many2one(
        comodel_name="product.trace",
        string="Lot/Serial",
        compute="_compute_trace_id",
        store=True,
        domain="[('id', 'in', allowed_trace_ids)]",
        check_company=True,
        help="Products repaired are all belonging to this lot",
    )
    tracking = fields.Selection(
        related="product_id.tracking",
        string="Product Tracking",
        readonly=False,
    )

    picking_type_id = fields.Many2one(
        comodel_name="stock.picking.type",
        string="Operation Type",
        compute="_compute_picking_type_id",
        precompute=True,
        store=True,
        index=True,
        copy=True,
        readonly=False,
        required=True,
        domain="[('code', '=', 'repair_operation'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    reference_ids = fields.Many2many(
        comodel_name="stock.reference",
        relation="stock_reference_repair_rel",
        column1="repair_id",
        column2="reference_id",
        string="References",
        copy=False,
    )
    location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Component Source Location",
        compute="_compute_location_id",
        precompute=True,
        store=True,
        index=True,
        readonly=False,
        required=True,
        check_company=True,
        help="This is the location where the components of product to repair is located.",
    )
    product_location_src_id = fields.Many2one(
        comodel_name="stock.location",
        string="Product Source Location",
        compute="_compute_product_location_src_id",
        precompute=True,
        store=True,
        index=True,
        readonly=False,
        required=True,
        check_company=True,
        help="This is the location where the product to repair is located.",
    )
    product_location_dest_id = fields.Many2one(
        comodel_name="stock.location",
        string="Product Destination Location",
        compute="_compute_product_location_dest_id",
        precompute=True,
        store=True,
        index=True,
        readonly=False,
        required=True,
        check_company=True,
        help="This is the location where the repaired product is located.",
    )
    location_dest_id = fields.Many2one(
        comodel_name="stock.location",
        related="picking_type_id.default_location_dest_id",
        string="Added Parts Destination Location",
        depends=["picking_type_id"],
        readonly=True,
        required=True,
        check_company=True,
        help="This is the location where the repaired product is located.",
    )
    parts_location_id = fields.Many2one(
        comodel_name="stock.location",
        related="picking_type_id.default_remove_location_dest_id",
        string="Removed Parts Destination Location",
        depends=["picking_type_id"],
        readonly=True,
        required=True,
        check_company=True,
        help="This is the location where the repair parts are located.",
    )
    recycle_location_id = fields.Many2one(
        comodel_name="stock.location",
        string="Recycled Parts Destination Location",
        compute="_compute_recycle_location_id",
        precompute=True,
        store=True,
        index=True,
        readonly=False,
        required=True,
        check_company=True,
        help="This is the location where the repair parts are located.",
    )

    move_ids = fields.One2many(
        comodel_name="stock.move",
        inverse_name="repair_id",
        string="Parts",
        copy=True,
        domain=[("repair_line_type", "!=", False)],
        check_company=True,
    )
    parts_availability = fields.Char(
        string="Component Status",
        compute="_compute_parts_availability_and_state",
        help="Latest parts availability status for this RO. If green, then the RO's readiness status is ready.",
    )
    parts_availability_state = fields.Selection(
        selection=[
            ("available", "Available"),
            ("expected", "Expected"),
            ("late", "Late"),
        ],
        compute="_compute_parts_availability_and_state",
    )
    is_parts_available = fields.Boolean(
        string="All Parts are available",
        compute="_compute_availability_boolean",
        default=False,
        store=True,
    )
    is_parts_late = fields.Boolean(
        string="Any Part is late",
        compute="_compute_availability_boolean",
        default=False,
        store=True,
    )

    sale_order_id = fields.Many2one(
        comodel_name="sale.order",
        index="btree_not_null",
        copy=False,
        readonly=True,
        check_company=True,
        help="Sale Order from which the Repair Order comes from.",
    )
    sale_order_line_id = fields.Many2one(
        comodel_name="sale.order.line",
        copy=False,
        readonly=True,
        check_company=True,
        help="Sale Order Line from which the Repair Order comes from.",
    )
    repair_request = fields.Text(
        related="sale_order_line_id.name",
        string="Repair Request",
        help="Sale Order Line Description.",
    )

    picking_id = fields.Many2one(
        comodel_name="stock.picking",
        string="Transfer",
        index="btree_not_null",
        copy=False,
        domain="[('return_id', '!=', False), ('product_id', '=?', product_id)]",
        check_company=True,
        help="Transfer from which the product to be repaired is picked",
    )
    picking_product_ids = fields.One2many(
        comodel_name="product.product",
        compute="_compute_picking_product_ids",
    )
    picking_product_id = fields.Many2one(related="picking_id.product_id")
    allowed_trace_ids = fields.One2many(
        comodel_name="product.trace",
        compute="_compute_allowed_trace_ids",
    )
    has_uncomplete_moves = fields.Boolean(compute="_compute_has_uncomplete_moves")
    unreserve_visible = fields.Boolean(
        string="Allowed to Unreserve Production",
        compute="_compute_reservation_visibility",
        help="Technical field to check when we can unreserve",
    )
    reserve_visible = fields.Boolean(
        string="Allowed to Reserve Production",
        compute="_compute_reservation_visibility",
        help="Technical field to check when we can reserve quantities",
    )
    picking_type_visible = fields.Boolean(compute="_compute_picking_type_visible")

    def _compute_picking_type_visible(self) -> None:
        repair_type_by_company = dict(
            self.env["stock.picking.type"]._read_group(
                [
                    ("code", "=", "repair_operation"),
                    ("company_id", "in", self.company_id.ids),
                ],
                groupby=["company_id"],
                aggregates=["__count"],
            )
        )
        for ro in self:
            ro.picking_type_visible = repair_type_by_company.get(ro.company_id, 0) > 1

    @api.depends("product_id", "picking_id", "trace_id")
    def _compute_product_qty(self):
        for repair in self:
            if repair.picking_id:
                if repair.tracking in ["serial", "lot"] and repair.trace_id:
                    lot_move_lines = repair.picking_id.move_line_ids.filtered_domain(
                        [
                            ("product_id", "=", repair.product_id.id),
                            ("trace_id", "=", repair.trace_id.id),
                        ]
                    )
                    repair.product_qty = sum(lot_move_lines.mapped("quantity"))
                else:
                    product_moves = repair.picking_id.move_ids.filtered_domain(
                        [("product_id", "=", repair.product_id.id)]
                    )
                    repair.product_qty = sum(product_moves.mapped("quantity"))
            else:
                repair.product_qty = 1.0

    @api.depends(
        "product_id",
        "product_id.uom_id",
        "product_id.uom_ids",
        "product_id.seller_ids",
        "product_id.seller_ids.product_uom_id",
    )
    def _compute_allowed_uom_ids(self):
        for repair in self:
            repair.allowed_uom_ids = (
                repair.product_id.uom_id
                | repair.product_id.uom_ids
                | repair.product_id.seller_ids.product_uom_id
            )

    @api.depends("picking_id")
    def _compute_partner_id(self):
        for repair in self:
            repair.partner_id = repair.picking_id.partner_id

    @api.depends("picking_id")
    def _compute_picking_product_ids(self) -> None:
        for repair in self:
            repair.picking_product_ids = repair.picking_id.move_ids.product_id

    @api.depends(
        "product_id",
        "company_id",
        "picking_id",
        "picking_id.move_ids",
        "picking_id.move_ids.trace_ids",
    )
    def _compute_allowed_trace_ids(self) -> None:
        for repair in self:
            domain = Domain("product_id", "=", repair.product_id.id)
            if repair.picking_id:
                domain &= Domain("id", "in", repair.picking_id.move_ids.trace_ids.ids)
            repair.allowed_trace_ids = self.env["product.trace"].search(domain)

    @api.depends("product_id", "product_id.uom_id")
    def _compute_product_uom_id(self):
        for repair in self:
            if not repair.product_id:
                repair.product_uom_id = False
            elif not repair.product_uom_id:
                repair.product_uom_id = repair.product_id.uom_id

    @api.depends("product_id", "trace_id", "trace_id.product_id", "picking_id")
    def _compute_trace_id(self) -> None:
        for repair in self:
            if (
                repair.product_id
                and repair.trace_id
                and repair.trace_id.product_id != repair.product_id
            ) or not repair.product_id:
                repair.trace_id = False
            elif len(repair.picking_id.move_ids.trace_ids) == 1:
                repair.trace_id = repair.picking_id.move_ids.trace_ids

    @api.depends("company_id")
    def _compute_picking_type_id(self):
        picking_type_by_company = self._get_picking_type()
        for ro in self:
            ro.picking_type_id = picking_type_by_company.get(
                (ro.company_id, ro.user_id)
            ) or picking_type_by_company.get((ro.company_id, False))

    @api.depends("picking_type_id")
    def _compute_location_id(self):
        for repair in self:
            repair.location_id = repair.picking_type_id.default_location_src_id

    @api.depends("picking_type_id")
    def _compute_product_location_src_id(self) -> None:
        for record in self:
            record.product_location_src_id = (
                record.picking_type_id.default_product_location_src_id
            )

    @api.depends("picking_type_id")
    def _compute_product_location_dest_id(self) -> None:
        for record in self:
            record.product_location_dest_id = (
                record.picking_type_id.default_product_location_dest_id
            )

    @api.depends("picking_type_id")
    def _compute_recycle_location_id(self) -> None:
        for repair in self:
            repair.recycle_location_id = (
                repair.picking_type_id.default_recycle_location_dest_id
            )

    @api.depends(
        "state",
        "schedule_date",
        "move_ids",
        "move_ids.forecast_availability",
        "move_ids.date_planned_forecast",
    )
    def _compute_parts_availability_and_state(self) -> None:
        _debug.perf.count("repair_parts_availability_compute", repairs=self)
        repairs = self.filtered(lambda ro: ro.state in ("confirmed", "under_repair"))
        repairs.parts_availability_state = "available"
        repairs.parts_availability = self.env._("Available")

        other_repairs = self - repairs
        other_repairs.parts_availability = False
        other_repairs.parts_availability_state = False

        all_moves = repairs.move_ids
        all_moves._fields["forecast_availability"].compute_value(all_moves)
        for repair in repairs:
            if any(
                move.product_id
                and move.product_id.uom_id.compare(
                    move.forecast_availability, move.product_qty
                )
                < 0
                for move in repair.move_ids
            ):
                repair.parts_availability = self.env._("Not Available")
                repair.parts_availability_state = "late"
                continue
            forecast_date = max(
                repair.move_ids.filtered("date_planned_forecast").mapped(
                    "date_planned_forecast"
                ),
                default=False,
            )
            if not forecast_date:
                continue
            repair.parts_availability = self.env._(
                "Exp %s", format_date(self.env, forecast_date)
            )
            if repair.schedule_date:
                repair.parts_availability_state = (
                    "late" if forecast_date > repair.schedule_date else "expected"
                )

    @api.depends("parts_availability_state")
    def _compute_availability_boolean(self) -> None:
        self.is_parts_available, self.is_parts_late = False, False
        for repair in self:
            if not repair.parts_availability_state:
                continue
            if repair.parts_availability_state == "available":
                repair.is_parts_available = True
            elif repair.parts_availability_state == "late":
                repair.is_parts_late = True

    @api.depends(
        "move_ids.quantity",
        "move_ids.product_uom_qty",
        "move_ids.product_uom_id.rounding",
    )
    def _compute_has_uncomplete_moves(self) -> None:
        for repair in self:
            repair.has_uncomplete_moves = any(
                move.product_uom_id
                and move.product_uom_id.compare(move.quantity, move.product_uom_qty) < 0
                for move in repair.move_ids
            )

    @api.depends("move_ids", "state", "move_ids.product_uom_qty")
    def _compute_reservation_visibility(self) -> None:
        for repair in self:
            repair.unreserve_visible = repair.state not in (
                "draft",
                "done",
                "cancel",
            ) and any(repair.move_ids.move_line_ids.mapped("quantity_product_uom"))
            repair.reserve_visible = repair.state in (
                "confirmed",
                "under_repair",
            ) and any(
                not move.picked
                and move.product_uom_qty
                and move.state in ["confirmed", "partially_available"]
                for move in repair.move_ids
            )

    @api.onchange("product_uom_id")
    def onchange_product_uom(self):
        res = {}
        if not self.product_id or not self.product_uom_id:
            return res
        return res

    @api.onchange("location_id", "picking_id")
    def _onchange_location_picking(self) -> dict | None:
        location_warehouse = self.location_id.warehouse_id
        picking_warehouse = self.picking_id.location_dest_id.warehouse_id
        if (
            location_warehouse
            and picking_warehouse
            and location_warehouse != picking_warehouse
        ):
            return {
                "warning": {
                    "title": self.env._("Warning"),
                    "message": self.env._(
                        "Note that the warehouses of the return and repair locations don't match!"
                    ),
                },
            }
        return None

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        if (
            "picking_id" not in res
            and "picking_id" in fields
            and "default_repair_picking_id" in self.env.context
        ):
            res["picking_id"] = self.env.context.get("default_repair_picking_id")
        if (
            "trace_id" not in res
            and "trace_id" in fields
            and "default_repair_lot_id" in self.env.context
        ):
            res["trace_id"] = self.env.context.get("default_repair_lot_id")
        return res

    @api.model_create_multi
    def create(self, vals_list):
        _debug.lifecycle("repair_create", count=len(vals_list))
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == "New":
                picking_type = self._picking_type_for_create(vals)
                vals["name"] = picking_type.sequence_id.next_by_id()
            if not vals.get("reference_ids"):
                vals["reference_ids"] = [
                    Command.link(
                        self.env["stock.reference"]
                        .sudo()
                        .create({"name": vals["name"]})
                        .id
                    )
                ]
        return super().create(vals_list)

    @api.model
    def _picking_type_for_create(self, vals):
        _debug.logic("repair_picking_type_for_create", repairs=self)
        defaults = self.default_get(["picking_type_id", "company_id", "user_id"])
        if picking_type_id := vals.get(
            "picking_type_id", defaults.get("picking_type_id")
        ):
            return self.env["stock.picking.type"].browse(picking_type_id)
        return self.new(
            {
                "company_id": vals.get("company_id", defaults.get("company_id")),
                "user_id": vals.get("user_id", defaults.get("user_id")),
            }
        ).picking_type_id

    def write(self, vals):
        _debug.lifecycle("repair_write", repairs=self, fields=len(vals))
        moves_to_reassign = self.env["stock.move"]
        if vals.get("picking_type_id"):
            picking_type = self.env["stock.picking.type"].browse(
                vals.get("picking_type_id")
            )
            for repair in self:
                if repair.state in ("cancel", "done"):
                    continue
                if picking_type != repair.picking_type_id:
                    repair.name = picking_type.sequence_id.next_by_id()
                    moves_to_reassign |= repair.move_ids
        res = super().write(vals)
        if "product_id" in vals and self.tracking == "serial":
            self.write({"product_qty": 1.0})

        for repair in self:
            has_modified_location = any(
                key in vals for key in MAP_REPAIR_TO_PICKING_LOCATIONS
            )
            if has_modified_location:
                repair.move_ids._set_repair_locations()
            if "schedule_date" in vals:
                (repair.move_id + repair.move_ids).filtered(
                    lambda m: m.state not in ("done", "cancel")
                ).write({"date": repair.schedule_date})
            if "under_warranty" in vals:
                repair._update_sale_order_line_price()
        if moves_to_reassign:
            moves_to_reassign._unreserve()
            moves_to_reassign._filtered_to_assign_at_confirm()._action_assign()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_except_confirmed(self) -> None:
        _debug.logic("repair_unlink_guard", repairs=self)
        repairs_to_cancel = self.filtered(lambda ro: ro.state != "cancel")
        repairs_to_cancel.action_repair_cancel()

    def action_generate_serial(self):
        _debug.lifecycle("repair_serial_generate", repairs=self)
        self.check_singleton()
        Lot = self.env["product.trace"]
        self.trace_id = Lot.create(
            Lot._prepare_next_lot_vals(self.company_id, self.product_id)
        )

    def action_assign(self):
        _debug.pipeline("repair_assign", repairs=self)
        return self.move_ids._action_assign()

    def action_create_sale_order(self):
        _debug.pipeline("repair_sale_order_create", repairs=self)
        if any(repair.sale_order_id for repair in self):
            concerned_ro = self.filtered("sale_order_id")
            ref_str = "\n".join(ro.name for ro in concerned_ro)
            raise UserError(
                self.env._(
                    "You cannot create a quotation for a repair order that is already linked to an existing sale order.\nConcerned repair order(s):\n%(ref_str)s",
                    ref_str=ref_str,
                ),
            )
        if any(not repair.partner_id for repair in self):
            concerned_ro = self.filtered(lambda ro: not ro.partner_id)
            ref_str = "\n".join(ro.name for ro in concerned_ro)
            raise UserError(
                self.env._(
                    "You need to define a customer for a repair order in order to create an associated quotation.\nConcerned repair order(s):\n%(ref_str)s",
                    ref_str=ref_str,
                ),
            )
        sale_order_values_list = [
            {
                "company_id": self.company_id.id,
                "partner_id": self.partner_id.id,
                "warehouse_id": self.picking_type_id.warehouse_id.id,
                "repair_order_ids": [Command.link(repair.id)],
                "origin": repair.name,
            }
            for repair in self
        ]
        self.env["sale.order"].create(sale_order_values_list)
        self.move_ids._create_repair_sale_order_line()
        return self.action_view_sale_order()

    def action_repair_cancel(self):
        _debug.lifecycle("repair_cancel", repairs=self)
        if any(repair.state == "done" for repair in self):
            raise UserError(
                self.env._(
                    "You cannot cancel a Repair Order that's already been completed"
                )
            )
        for repair in self:
            if repair.sale_order_id:
                repair.sale_order_line_id.write(
                    {"product_qty": 0.0}
                )
        self.move_ids._action_cancel()
        return self.write({"state": "cancel"})

    def action_repair_cancel_draft(self) -> None:
        _debug.lifecycle("repair_back_to_draft", repairs=self)
        if self.filtered(lambda repair: repair.state != "cancel"):
            self.action_repair_cancel()
        sale_line_to_update = self.move_ids.sale_line_id.filtered(
            lambda l: (
                l.order_id.state != "cancel" and l.product_uom_id.is_zero(l.product_qty)
            )
        )
        sale_line_to_update.move_ids._update_repair_sale_order_line()
        self.move_ids.state = "draft"
        self.state = "draft"

    def action_repair_done(self):

        _debug.pipeline("repair_done_enter", repairs=self)
        precision = self.env["decimal.precision"].get_precision("Product Unit")
        product_move_vals = []

        self.move_ids.filtered(
            lambda m: m.product_uom_id.is_zero(m.quantity)
        )._action_cancel()

        no_service_policy = "service_policy" not in self.env["product.template"]
        for repair in self:
            if all(not move.picked for move in repair.move_ids):
                repair.move_ids.picked = True
            if repair.sale_order_line_id:
                ro_origin_product = repair.sale_order_line_id.product_template_id
                if ro_origin_product.type == "service" and (
                    no_service_policy
                    or ro_origin_product.service_policy == "ordered_prepaid"
                ):
                    repair.sale_order_line_id.qty_transferred = (
                        repair.sale_order_line_id.product_qty
                    )
            if not repair.product_id:
                continue

            if (
                repair.product_id.product_tmpl_id.tracking != "none"
                and not repair.trace_id
            ):
                raise ValidationError(
                    self.env._(
                        "Serial number is required for product to repair : %s",
                        repair.product_id.display_name,
                    )
                )

            owner_id = False
            available_qty_owner = self.env["stock.quant"]._get_available_quantity(
                repair.product_id,
                repair.location_id,
                repair.trace_id,
                owner_id=repair.partner_id,
                strict=True,
            )
            if (
                float_compare(
                    available_qty_owner, repair.product_qty, precision_digits=precision
                )
                >= 0
            ):
                owner_id = repair.partner_id.id

            product_move_vals.append(
                {
                    "product_id": repair.product_id.id,
                    "product_uom_id": repair.product_uom_id.id
                    or repair.product_id.uom_id.id,
                    "product_uom_qty": repair.product_qty,
                    "partner_id": repair.partner_id.id,
                    "location_id": repair.product_location_src_id.id,
                    "location_dest_id": repair.product_location_dest_id.id,
                    "picked": True,
                    "picking_id": False,
                    "move_line_ids": [
                        Command.create(
                            {
                                "product_id": repair.product_id.id,
                                "trace_id": repair.trace_id.id,
                                "product_uom_id": repair.product_uom_id.id
                                or repair.product_id.uom_id.id,
                                "quantity": repair.product_qty,
                                "package_id": False,
                                "result_package_id": False,
                                "owner_id": owner_id,
                                "location_id": repair.product_location_src_id.id,
                                "company_id": repair.company_id.id,
                                "location_dest_id": repair.product_location_dest_id.id,
                                "consume_line_ids": [
                                    Command.set(repair.move_ids.move_line_ids.ids)
                                ],
                            }
                        )
                    ],
                    "repair_id": repair.id,
                    "origin": repair.name,
                    "company_id": repair.company_id.id,
                }
            )

        product_moves = self.env["stock.move"].create(product_move_vals)
        repair_move = {m.repair_id.id: m for m in product_moves}
        for repair in self:
            move_id = repair_move.get(repair.id, False)
            if move_id:
                repair.move_id = move_id
        all_moves = self.move_ids + product_moves
        all_moves._action_done(cancel_backorder=True)

        self.state = "done"

    def action_repair_end(self):
        _debug.lifecycle("repair_end", repairs=self)
        if self.filtered(lambda repair: repair.state != "under_repair"):
            raise UserError(
                self.env._("Repair must be under repair in order to end reparation.")
            )
        partial_moves = set()
        picked_moves = set()
        for move in self.move_ids:
            if move.product_uom_id.compare(move.quantity, move.product_uom_qty) < 0:
                partial_moves.add(move.id)
            if move.picked:
                picked_moves.add(move.id)
        return self.action_repair_done()

    def action_repair_start(self):
        _debug.lifecycle("repair_start", repairs=self)
        if self.filtered(lambda repair: repair.state != "confirmed"):
            self._action_repair_confirm()
        return self.write({"state": "under_repair"})

    def action_unreserve(self):
        _debug.lifecycle("repair_unreserve", repairs=self)
        return self.move_ids.filtered(
            lambda m: m.state in ("assigned", "partially_available")
        )._unreserve()

    def action_validate(self):
        _debug.pipeline("repair_validate_enter", repairs=self)
        self.check_singleton()
        if self.filtered(
            lambda repair: any(m.product_uom_qty < 0 for m in repair.move_ids)
        ):
            raise UserError(self.env._("You can not enter negative quantities."))
        if not self.product_id or not self.product_id.is_storable:
            return self._action_repair_confirm()
        precision = self.env["decimal.precision"].get_precision("Product Unit")
        available_qty_owner = sum(
            self.env["stock.quant"]
            .search(
                [
                    ("product_id", "=", self.product_id.id),
                    ("location_id", "=", self.product_location_src_id.id),
                    ("trace_id", "=", self.trace_id.id),
                    ("owner_id", "=", self.partner_id.id),
                ]
            )
            .mapped("quantity")
        )
        available_qty_noown = sum(
            self.env["stock.quant"]
            .search(
                [
                    ("product_id", "=", self.product_id.id),
                    ("location_id", "=", self.product_location_src_id.id),
                    ("trace_id", "=", self.trace_id.id),
                    ("owner_id", "=", False),
                ]
            )
            .mapped("quantity")
        )
        repair_qty = self.product_uom_id._get_quantity_in_unit(
            self.product_qty, self.product_id.uom_id
        )
        for available_qty in [available_qty_owner, available_qty_noown]:
            if (
                float_compare(available_qty, repair_qty, precision_digits=precision)
                >= 0
            ):
                return self._action_repair_confirm()

        return {
            "name": self.env._(
                "%(product)s: Insufficient Quantity To Repair",
                product=self.product_id.display_name,
            ),
            "view_mode": "form",
            "res_model": "wizard.repair.order.confirm.insufficient.stock",
            "view_id": self.env.ref(
                "repair.stock_warn_insufficient_qty_repair_form_view"
            ).id,
            "type": "ir.actions.act_window",
            "context": {
                "default_product_id": self.product_id.id,
                "default_location_id": self.product_location_src_id.id,
                "default_repair_id": self.id,
                "default_quantity": repair_qty,
                "default_product_uom_name": self.product_id.uom_name,
            },
            "target": "new",
        }

    def action_view_sale_order(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "views": [[False, "form"]],
            "res_id": self.sale_order_id.id,
        }

    def print_repair_order(self):
        return self.env.ref("repair.action_report_repair_order").report_action(self)

    def _action_repair_confirm(self):
        _debug.pipeline("repair_confirm_enter", repairs=self)
        repairs_to_confirm = self.filtered(lambda repair: repair.state == "draft")
        repairs_to_confirm._check_company()
        repairs_to_confirm.move_ids._check_company()
        repairs_to_confirm.move_ids._update_procure_method(
            picking_type_code="repair_operation"
        )
        repairs_to_confirm.move_ids._action_confirm()
        repairs_to_confirm.move_ids._trigger_scheduler()
        repairs_to_confirm.write({"state": "confirmed"})
        return True

    def _get_location(self, field):
        return self.picking_type_id[MAP_REPAIR_TO_PICKING_LOCATIONS[field]]

    def _get_picking_type(self):
        companies = self.company_id or self.env.company
        if not self:
            default_warehouse = self.env.user.with_company(
                companies.id
            )._get_default_warehouse_id()
            if default_warehouse and default_warehouse.repair_type_id:
                return {(companies, self.env.user): default_warehouse.repair_type_id}

        picking_type_by_company_user = {}
        without_default_warehouse_companies = set()
        for company, user in unique((r.company_id, r.user_id) for r in self):
            default_warehouse = user.with_company(
                company.id
            )._get_default_warehouse_id()
            if default_warehouse and default_warehouse.repair_type_id:
                picking_type_by_company_user[(company, user)] = (
                    default_warehouse.repair_type_id
                )
            else:
                without_default_warehouse_companies.add(company.id)

        if not without_default_warehouse_companies:
            return picking_type_by_company_user

        domain = [
            ("code", "=", "repair_operation"),
            (
                "warehouse_id.company_id",
                "in",
                list(without_default_warehouse_companies),
            ),
        ]

        picking_types = self.env["stock.picking.type"].search_read(
            domain, ["company_id"], load=False
        )
        for picking_type in picking_types:
            if (picking_type.company_id, False) not in picking_type_by_company_user:
                picking_type_by_company_user[(picking_type.company_id, False)] = (
                    picking_type
                )
        return picking_type_by_company_user

    def _update_sale_order_line_price(self) -> None:
        _debug.pipeline("repair_sale_line_price_update", repairs=self)
        for repair in self:
            add_moves = repair.move_ids.filtered(
                lambda m: m.repair_line_type == "add" and m.sale_line_id
            )
            if repair.under_warranty:
                add_moves.sale_line_id.write(
                    {"price_unit": 0.0, "price_unit_auto": 0.0}
                )
            else:
                add_moves.sale_line_id._compute_price_and_discount()


    def action_add_from_catalog(self):
        res = super().action_add_from_catalog()
        res["search_view_id"] = [
            self.env.ref("repair.product_view_search_catalog").id,
            "search",
        ]
        return res

    def _get_order_line_values(self, child_field=False) -> dict:
        default_data = super()._get_order_line_values(child_field)
        new_default_data = self.env["stock.move"]._get_product_catalog_lines_data(
            parent_record=self
        )

        return {**default_data, **new_default_data}

    def _get_domain_product_catalog(self):
        return super()._get_domain_product_catalog() & Domain("type", "=", "consu")

    def _get_product_catalog_order_data(self, products, **kwargs):
        product_catalog = super()._get_product_catalog_order_data(products, **kwargs)
        for product in products:
            product_catalog[product.id] |= self._get_product_price_and_data(product)
        return product_catalog

    def _get_product_price_and_data(self, product):
        self.check_singleton()
        return {"price": product.list_price}

    def _get_product_catalog_record_lines(self, product_ids, **kwargs):
        grouped_lines = defaultdict(lambda: self.env["stock.move"])

        for line in self.move_ids:
            if line.product_id.id in product_ids:
                grouped_lines[line.product_id] |= line

        return grouped_lines

    def _is_display_stock_in_catalog(self) -> bool:
        return True

    def _update_order_line_info(self, product_id, quantity, **kwargs):
        move = self.move_ids.filtered(lambda e: e.product_id.id == product_id)
        if move:
            if quantity != 0:
                move.product_uom_qty = quantity
            else:
                move.unlink()
        elif quantity > 0:
            move = self.env["stock.move"].create(
                {
                    "repair_id": self.id,
                    "product_uom_qty": quantity,
                    "product_id": product_id,
                    "location_id": self.location_id.id,
                    "location_dest_id": self.location_dest_id.id,
                    "repair_line_type": "add",
                }
            )

        return self.env["product.product"].browse(product_id).list_price


    def _message_post_prepare_values(self, post_values) -> None:
        super()._message_post_prepare_values(post_values)
        post_values.setdefault("notify_author_mention", True)


class RepairTags(models.Model):

    _name = "repair.tags"
    _description = "Repair Tags"
    _inherit = ["mixin.tag"]
