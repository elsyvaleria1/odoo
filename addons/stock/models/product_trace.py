from collections import defaultdict
from collections.abc import Iterable

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import DOMAIN_PREDICATES

from odoo.addons.stock.tools.quantity import (
    QuantityFilters,
    get_domain_quantity_in_python,
)

_debug = DebugLog(__name__)


class ProductTrace(models.Model):
    _inherit = "product.trace"

    product_id = fields.Many2one(
        domain="[('tracking', '!=', 'none'), ('is_storable', '=', True)] +"
        " ([('product_tmpl_id', '=', context['default_product_tmpl_id'])] if context.get('default_product_tmpl_id') else [])",
    )
    quant_ids = fields.One2many(
        comodel_name="stock.quant",
        inverse_name="trace_id",
        string="Quants",
        readonly=True,
    )
    product_qty = fields.Float(
        string="On Hand Quantity",
        compute="_compute_product_qty",
        search="_search_product_qty",
    )
    delivery_ids = fields.Many2many(
        comodel_name="stock.picking",
        string="Transfers",
        compute="_compute_delivery_ids",
    )
    count_transfer_outgoing = fields.Count(
        count_of="delivery_ids",
        string="Delivery order count",
    )
    partner_ids = fields.Many2many(
        comodel_name="res.partner",
        compute="_compute_partner_ids",
        search="_search_partner_ids",
    )
    location_id = fields.Many2one(
        comodel_name="stock.location",
        compute="_compute_location_id",
        inverse="_inverse_location_id",
        store=True,
        readonly=False,
        group_expand="_read_group_location_id",
        domain="[('usage', '!=', 'view')]",
    )

    @_debug.perf.timed
    @api.model_create_multi
    def create(self, vals_list):
        self._check_lots_allowed(
            {
                product_id
                for product_id in (
                    *(vals.get("product_id") for vals in vals_list),
                    self.env.context.get("default_product_id"),
                )
                if product_id
            }
        )
        return super().create(vals_list)

    @_debug.perf.timed
    def write(self, vals):
        if any(field in vals for field in ("name", "product_id", "company_id")):
            self._check_lots_allowed(
                {vals.get("product_id"), *self.product_id.ids} - {None, False}
            )
        if vals.get("company_id"):
            for lot in self:
                quant_companies = lot.quant_ids.filtered(
                    lambda q: q.quantity
                ).location_id.company_id
                if any(company.id != vals["company_id"] for company in quant_companies):
                    raise UserError(
                        self.env._(
                            "You cannot change the company of a lot/serial number currently in a location belonging to another company."
                        ),
                    )
        if "product_id" in vals and any(
            vals["product_id"] != lot.product_id.id for lot in self
        ):
            move_lines = self.env["stock.move.line"].search_count(
                [
                    ("trace_id", "in", self.ids),
                    ("product_id", "!=", vals["product_id"]),
                ],
                limit=1,
            )
            if move_lines:
                raise UserError(
                    self.env._(
                        "You are not allowed to change the product linked to a serial or lot number "
                        "if some stock moves have already been created with that number. "
                        "This would lead to inconsistencies in your stock."
                    ),
                )
        return super().write(vals)

    @api.depends("quant_ids", "quant_ids.quantity", "quant_ids.location_id")
    def _compute_location_id(self):
        for lot in self:
            quants = lot.quant_ids.filtered(
                lambda q: q.product_uom_id.compare(q.quantity, 0) > 0
            )
            lot.location_id = (
                quants.location_id if len(quants.location_id) == 1 else False
            )

    @api.depends_context(
        "owner_id",
        "package_id",
        "to_date",
        "location",
        "warehouse_id",
        "search_location",
        "search_warehouse",
        "allowed_company_ids",
        "strict",
    )
    @api.depends("quant_ids", "quant_ids.quantity")
    def _compute_product_qty(self):
        qty_by_lot = self._get_product_qty_by_lot(Domain("trace_id", "in", self.ids))
        for lot in self:
            lot.product_qty = qty_by_lot.get(lot, 0.0)

    def _compute_delivery_ids(self) -> None:
        delivery_ids_by_lot = self._get_delivery_ids_by_lot()
        for lot in self:
            lot.delivery_ids = delivery_ids_by_lot.get(lot.id, [])

    @api.depends("delivery_ids")
    def _compute_partner_ids(self) -> None:
        for lot in self:
            lot.partner_ids = self._get_partners_from_deliveries(lot.delivery_ids)

    def _search_product_qty(self, operator, value):
        op = DOMAIN_PREDICATES.get(operator)
        if not op:
            return get_domain_quantity_in_python(self, "product_qty", operator, value)
        if isinstance(value, Iterable) and not isinstance(value, str):
            value = {float(v) for v in value}
        else:
            value = float(value)
        qty_by_lot = self._get_product_qty_by_lot(Domain("trace_id", "!=", False))
        ids = [lot.id for lot, qty in qty_by_lot.items() if op(qty, value)]

        if op(0.0, value):
            lots_w_qty = [lot.id for lot in qty_by_lot]
            return ["|", ("id", "in", ids), ("id", "not in", lots_w_qty)]
        return [("id", "in", ids)]

    def _search_partner_ids(self, operator, value):
        if operator in Domain.NEGATIVE_OPERATORS or not isinstance(value, (Iterable)):
            return NotImplemented
        is_no_partner = operator == "in" and list(value) == [False]
        domain = Domain(
            [
                ("trace_id", "!=", False),
                ("state", "=", "done"),
            ]
        )
        if is_no_partner:
            domain &= Domain("picking_partner_id", "!=", False) | Domain(
                "move_partner_id", "!=", False
            )
        else:
            domain &= Domain.OR(
                [
                    Domain("picking_partner_id", operator, value),
                    Domain("move_partner_id", operator, value),
                ]
            )
        domain &= self._get_domain_outgoing_move_lines()
        move_lines = self.env["stock.move.line"].search(domain)

        if is_no_partner:
            return [("id", "not in", move_lines.trace_id.ids)]
        return [("id", "in", move_lines.trace_id.ids)]

    def _inverse_location_id(self) -> None:
        for lot in self:
            quants = lot.quant_ids.filtered(
                lambda quant: quant.product_uom_id.compare(quant.quantity, 0) > 0
            )
            if len(quants.location_id) > 1:
                raise UserError(
                    self.env._(
                        "You can only move a lot/serial to a new location if it exists in a single location."
                    ),
                )
            if not quants:
                continue
            message = self.env._("Lot/Serial Number Relocated")
            breaking = quants._filtered_breaking_a_package()
            if _debug.pipeline.enabled:
                _debug.pipeline(
                    "lot_relocated",
                    lot=lot.id,
                    location=lot.location_id.id,
                    breaking=breaking,
                    intact=quants - breaking,
                )
            if breaking:
                breaking.move_quants(
                    location_dest_id=lot.location_id,
                    message=message,
                    unpack=True,
                )
            intact = quants - breaking
            if intact:
                intact.move_quants(
                    location_dest_id=lot.location_id,
                    message=message,
                )

    def action_lot_open_quants(self):
        self.check_singleton()
        quants = self.with_context(search_default_trace_id=self.id, create=False)
        if self.env.user.has_group("stock.group_stock_manager"):
            quants = quants.with_context(inventory_mode=True)
        return quants.env["stock.quant"]._get_action_view_quants(
            products=self.product_id
        )

    def action_lot_open_transfers(self):
        self.check_singleton()

        action = {"res_model": "stock.picking", "type": "ir.actions.act_window"}
        if len(self.delivery_ids) == 1:
            action.update({"view_mode": "form", "res_id": self.delivery_ids[0].id})
        else:
            action.update(
                {
                    "name": self.env._("Delivery orders of %s", self.display_name),
                    "domain": [("id", "in", self.delivery_ids.ids)],
                    "view_mode": "list,form",
                }
            )
        return action

    def _read_group_location_id(self, locations, domain):
        partner_locations = locations.search(
            [("usage", "in", ("customer", "supplier"))]
        )
        warehouses = self.env["stock.warehouse"].search([])
        return partner_locations + warehouses.lot_stock_id

    @_debug.perf.timed
    def _get_product_qty_by_lot(self, lot_domain):
        Product = self.env["product.product"]
        filters = QuantityFilters(
            owner_id=self.env.context.get("owner_id"),
            package_id=self.env.context.get("package_id"),
        )
        domain_quant = Product._narrow_quantity_domains(
            lot_domain
            & self.env["stock.location"]._get_domains_quantity_from_context()[0],
            Domain.TRUE,
            Domain.TRUE,
            filters,
        )[0]
        qty_by_lot = dict(
            self.env["stock.quant"]._read_group(
                domain_quant, ["trace_id"], ["quantity:sum"]
            )
        )
        to_date, dates_in_the_past = Product._normalize_quantities_to_date(
            self.env.context.get("to_date")
        )
        if not dates_in_the_past:
            return qty_by_lot
        in_leaves, out_leaves = Product._get_domains_quantity_leaves(filters)
        move_in_qty_by_lot, move_out_qty_by_lot = Product._read_done_quantities_after(
            to_date, lot_domain & in_leaves, lot_domain & out_leaves, "trace_id"
        )
        return {
            lot: qty_by_lot.get(lot, 0.0)
            - move_in_qty_by_lot.get(lot, 0.0)
            + move_out_qty_by_lot.get(lot, 0.0)
            for lot in set(qty_by_lot)
            | set(move_in_qty_by_lot)
            | set(move_out_qty_by_lot)
        }

    @api.model
    def _get_domain_accessible_location(self) -> list:
        return [
            "|",
            ("location_id", "=", False),
            (
                "location_id",
                "any",
                self.env["stock.location"]._get_domain_company_compatible(
                    self.env.companies.ids
                ),
            ),
        ]

    def _check_lots_allowed(self, product_ids):
        active_picking_id = self.env.context.get("active_picking_id", False)
        if active_picking_id:
            picking_id = self.env["stock.picking"].browse(active_picking_id)
            if picking_id and not picking_id.picking_type_id.use_create_lots:
                raise UserError(
                    self.env._(
                        'You are not allowed to create a lot or serial number with this operation type. To change this, go on the operation type and tick the box "Create New Lots/Serial Numbers".'
                    ),
                )

    def _get_partners_from_deliveries(self, pickings):
        return pickings.partner_id

    @api.model
    def _get_domain_outgoing_move_lines(self) -> Domain:
        return Domain(
            [
                "|",
                "|",
                ("picking_code", "=", "outgoing"),
                ("move_id.picking_code", "=", "outgoing"),
                ("produce_line_ids", "!=", False),
            ]
        )

    @_debug.perf.timed
    def _get_delivery_ids_by_lot(self) -> dict:
        all_lot_ids = set(self.ids)
        barren_lines = defaultdict(set)
        parent_map = defaultdict(set)

        queue = list(self.ids)
        depth = 0
        while queue:
            depth += 1
            domain = (
                Domain(
                    [
                        ("trace_id", "in", queue),
                        ("state", "=", "done"),
                    ]
                )
                & self._get_domain_outgoing_move_lines()
            )

            queue = []
            move_lines = self.env["stock.move.line"].search(domain)
            for line in move_lines:
                trace_id = line.trace_id.id

                produce_line_lot_ids = line.produce_line_ids.trace_id.ids
                if produce_line_lot_ids:
                    for child_lot_id in produce_line_lot_ids:
                        parent_map[child_lot_id].add(trace_id)
                else:
                    barren_lines[trace_id].add(line.id)

                next_lots = set(produce_line_lot_ids) - all_lot_ids
                all_lot_ids.update(next_lots)
                queue.extend(next_lots)

        _debug.perf.count(
            "delivery_ids_by_lot",
            lots=len(self),
            tree_lots=len(all_lot_ids),
            rounds=depth,
            parents=len(parent_map),
        )
        lots_to_propagate = set()
        delivery_by_lot = {trace_id: set() for trace_id in all_lot_ids}
        for trace_id, barren_line_ids in barren_lines.items():
            barren_move_lines = self.env["stock.move.line"].browse(barren_line_ids)
            delivery_by_lot[trace_id].update(barren_move_lines.picking_id.ids)
            lots_to_propagate.add(trace_id)

        while lots_to_propagate:
            trace_id = lots_to_propagate.pop()

            for parent_id in parent_map.get(trace_id, []):
                new_deliveries = delivery_by_lot[trace_id] - delivery_by_lot[parent_id]
                if new_deliveries:
                    delivery_by_lot[parent_id].update(new_deliveries)
                    lots_to_propagate.add(parent_id)

        return {
            trace_id: list(pickings) for trace_id, pickings in delivery_by_lot.items()
        }
