from collections import defaultdict
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools.misc import groupby as tools_groupby

_debug = DebugLog(__name__)


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    tracking = fields.Selection(
        related="product_id.tracking",
        depends=["product_id"],
    )
    reserved_trace_ids = fields.Many2many(
        comodel_name="product.trace",
        relation="rental_reserved_lot_rel",
        string="Reserved Lots",
        copy=False,
        group_expand="_read_group_expand_reserved_lot_ids",
        domain="[('product_id', '=', product_id)]",
    )
    available_reserved_lots = fields.Boolean(compute="_compute_available_reserved_lots")

    pickedup_trace_ids = fields.Many2many(
        comodel_name="product.trace",
        relation="rental_pickedup_lot_rel",
        copy=False,
        domain="[('product_id', '=', product_id)]",
    )
    returned_trace_ids = fields.Many2many(
        comodel_name="product.trace",
        relation="rental_returned_lot_rel",
        copy=False,
        domain="[('product_id', '=', product_id)]",
    )
    unavailable_trace_ids = fields.Many2many(
        comodel_name="product.trace",
        relation="unreturned_reserved_serial",
        compute="_compute_unavailable_lots",
        store=False,
    )

    @api.depends("reserved_trace_ids", "reservation_begin", "return_date")
    def _compute_available_reserved_lots(self) -> None:
        self.available_reserved_lots = True
        if not self._are_rental_pickings_enabled():
            return
        lines_to_check = self.filtered(
            lambda l: (
                l.is_rental
                and l.reserved_trace_ids
                and l.product_template_id.tracking == "serial"
            )
        )

        partner_location_ids = self.env["stock.location"].search(
            [("usage", "in", ["customer", "supplier"])]
        )

        for line in lines_to_check:
            company_id = line.order_id.company_id.id
            domain = [
                ("company_id", "=", company_id),
                ("state", "not in", ["done", "cancel"]),
                ("trace_id", "in", line.reserved_trace_ids.ids),
            ]
            leaving_move_lines_groups = self.env["stock.move.line"]._read_group(
                Domain.AND(
                    [
                        domain,
                        [
                            ("location_usage", "=", "internal"),
                            ("location_dest_id", "child_of", partner_location_ids.ids),
                        ],
                    ]
                ),
                groupby=["trace_id"],
                aggregates=["id:recordset"],
            )
            leaving_move_by_lot = {g[0].id: g[1] for g in leaving_move_lines_groups}
            incoming_move_lines_groups = self.env["stock.move.line"]._read_group(
                Domain.AND(
                    [
                        domain,
                        [
                            ("location_id", "child_of", partner_location_ids.ids),
                            ("location_dest_usage", "=", "internal"),
                        ],
                    ]
                ),
                groupby=["trace_id"],
                aggregates=["id:recordset"],
            )
            incoming_move_by_lot = {g[0].id: g[1] for g in incoming_move_lines_groups}
            for lot in line.reserved_trace_ids:
                trace_id = lot.ids[0]
                if trace_id in line.move_ids.trace_ids.ids:
                    continue
                in_stock = bool(
                    sum(
                        lot.quant_ids.filtered_domain(
                            [
                                ("location_id.usage", "in", ["internal", "transit"]),
                                (
                                    "location_id",
                                    "not in",
                                    partner_location_ids.child_internal_location_ids.ids,
                                ),
                                ("company_id", "=", company_id),
                            ]
                        ).mapped("quantity")
                    )
                )
                if in_stock:
                    leaving_move_line = leaving_move_by_lot.get(trace_id, False)
                    leaving = bool(
                        leaving_move_line
                        and (
                            leaving_move_line.move_id.date_deadline <= line.return_date
                            and not (
                                leaving_move_line.move_id.sale_line_id.return_date
                                and leaving_move_line.move_id.sale_line_id.return_date
                                <= line.reservation_begin
                            )
                        )
                    )
                    in_stock = not leaving
                else:
                    incoming_move_line = incoming_move_by_lot.get(trace_id, False)
                    incoming = bool(
                        incoming_move_line
                        and incoming_move_line.move_id.date_deadline
                        <= line.reservation_begin
                    )
                    in_stock = incoming
                if not in_stock:
                    line.available_reserved_lots = False
                    break

    def _partition_so_lines_by_rental_period(self):
        now = fields.Datetime.now()
        lines_grouping_key = {
            line.id: (
                line.reservation_begin,
                line.return_date,
                line.order_id.warehouse_id.id,
            )
            for line in self
        }

        def get_rental_period_key(line_id):
            return (
                max(lines_grouping_key[line_id][0], now),
                lines_grouping_key[line_id][1],
                lines_grouping_key[line_id][2],
            )

        return tools_groupby(self._ids, key=get_rental_period_key)

    @api.depends("reservation_begin", "return_date", "product_id")
    def _compute_qty_at_date(self) -> None:
        non_rental = self.filtered(lambda sol: not sol.is_rental)
        super(SaleOrderLine, non_rental)._compute_qty_at_date()
        rented_product_lines = (self - non_rental).filtered(
            lambda l: l.product_id and l.product_id.is_storable
        )
        line_default_values = {
            "qty_available_virtual_at_date": 0.0,
            "date_planned": False,
            "date_planned_forecast": False,
            "qty_free_today": 0.0,
            "qty_available_today": False,
        }
        for (
            from_date,
            to_date,
            warehouse_id,
        ), line_ids in rented_product_lines._partition_so_lines_by_rental_period():
            lines = self.env["sale.order.line"].browse(line_ids)
            for line in lines:
                if from_date <= fields.Datetime.now():
                    rentable_qty = line.product_id.with_context(
                        from_date=from_date, to_date=to_date, warehouse_id=warehouse_id
                    ).qty_available
                else:
                    rentable_qty = line.product_id.with_context(
                        from_date=False, to_date=from_date, warehouse_id=warehouse_id
                    ).qty_available_virtual
                    rentable_qty += (
                        line.product_id._get_virtual_unavailable_qty_in_rent(
                            pivot_date=from_date,
                            ignored_soline_id=line
                            and line.state == "draft"
                            and line.id,
                            warehouse_id=line.order_id.warehouse_id.id,
                        )
                    )
                rented_qty_during_period = line.product_id._get_unavailable_qty(
                    from_date,
                    to_date,
                    ignored_soline_id=line and line.id,
                    warehouse_id=line.order_id.warehouse_id.id,
                )
                qty_available_virtual_at_date = max(
                    rentable_qty - rented_qty_during_period, 0
                )
                line.update(
                    dict(
                        line_default_values,
                        qty_available_virtual_at_date=qty_available_virtual_at_date,
                        date_planned=from_date,
                        qty_free_today=qty_available_virtual_at_date,
                    )
                )
        ((self - non_rental) - rented_product_lines).update(line_default_values)

    @api.depends("is_rental")
    def _compute_qty_transferred_method(self) -> None:
        rental_lines = self.filtered("is_rental")
        super(SaleOrderLine, self - rental_lines)._compute_qty_transferred_method()
        rental_lines.qty_transferred_method = "manual"

    def _read_group_expand_reserved_lot_ids(self, lots, domain):
        domain = Domain.AND([domain, Domain("product_id.tracking", "!=", "none")])
        products = (
            self.env["sale.order.line"].search_fetch(domain, ["product_id"]).product_id
        )
        return lots + self.env["product.trace"]._get_available_lots(products)

    def write(self, vals):
        if (
            not any(
                key in vals
                for key in [
                    "qty_transferred",
                    "pickedup_trace_ids",
                    "qty_returned",
                    "returned_trace_ids",
                ]
            )
            or self._are_rental_pickings_enabled()
        ):
            _debug.logic("rental_moves_skipped", lines=self, reason="not_rental_write")
            return super().write(vals)

        old_vals = {}
        movable_confirmed_rental_lines = self.filtered(
            lambda sol: (
                sol.is_rental and sol.state == "done" and sol.product_id.type == "consu"
            )
        )
        for sol in movable_confirmed_rental_lines:
            old_vals[sol.id] = (
                (sol.pickedup_trace_ids, sol.returned_trace_ids)
                if sol.product_id.tracking == "serial"
                else (sol.qty_transferred, sol.qty_returned)
            )
            if (
                vals.get("pickedup_trace_ids", False)
                and vals["pickedup_trace_ids"][0][0] == 6
            ):
                pickedup_trace_ids = vals["pickedup_trace_ids"][0][2]
                if (
                    sol.product_qty == len(pickedup_trace_ids)
                    and pickedup_trace_ids != sol.reserved_trace_ids.ids
                ):
                    """ When setting the pickedup_lots:
                    If the total reserved quantity is picked_up we need to unreserve
                    the reserved_lots not picked to ensure the consistency of rental reservations.
                    NOTE: This is only guaranteed for generic 6, _, _ orm magic commands.
                    """
                    _debug.logic(
                        "reserved_lots_realigned",
                        line=sol,
                        lots=len(pickedup_trace_ids),
                    )
                    vals["reserved_trace_ids"] = vals["pickedup_trace_ids"]

        res = super().write(vals)

        _debug.pipeline(
            "rental_stock_write",
            lines=self,
            movable=movable_confirmed_rental_lines,
            fields=list(vals),
        )
        self._write_rental_lines(movable_confirmed_rental_lines, old_vals, vals)
        return res

    def _write_rental_lines(self, lines, old_vals, vals) -> None:
        if not lines:
            return

        lines.mapped("company_id").filtered(
            lambda company: not company.rental_loc_id
        )._create_rental_location()

        for sol in lines:
            sol = sol.with_company(sol.company_id)
            rented_location = sol.company_id.rental_loc_id
            stock_location = sol.order_id.warehouse_id.lot_stock_id
            if sol.product_id.tracking == "serial" and (
                vals.get("pickedup_trace_ids", False)
                or vals.get("returned_trace_ids", False)
            ):
                if vals.get("pickedup_trace_ids", False):
                    pickedup_lots = sol.pickedup_trace_ids - old_vals[sol.id][0]
                    removed_pickedup_lots = old_vals[sol.id][0] - sol.pickedup_trace_ids
                    sol._move_serials(pickedup_lots, stock_location, rented_location)
                    sol._return_serials(
                        removed_pickedup_lots, rented_location, stock_location
                    )
                if vals.get("returned_trace_ids", False):
                    returned_lots = sol.returned_trace_ids - old_vals[sol.id][1]
                    removed_returned_lots = old_vals[sol.id][1] - sol.returned_trace_ids
                    sol._move_serials(returned_lots, rented_location, stock_location)
                    sol._return_serials(
                        removed_returned_lots, stock_location, rented_location
                    )
            elif sol.product_id.tracking != "serial" and any(
                k in vals for k in ("qty_transferred", "qty_returned")
            ):
                qty_transferred_change = sol.qty_transferred - old_vals[sol.id][0]
                qty_returned_change = sol.qty_returned - old_vals[sol.id][1]
                if qty_transferred_change > 0:
                    sol._move_qty(
                        qty_transferred_change, stock_location, rented_location
                    )
                elif qty_transferred_change < 0:
                    sol._return_qty(
                        -qty_transferred_change, stock_location, rented_location
                    )

                if qty_returned_change > 0.0:
                    sol._move_qty(qty_returned_change, rented_location, stock_location)
                elif qty_returned_change < 0.0:
                    sol._return_qty(
                        -qty_returned_change, rented_location, stock_location
                    )

    def _move_serials(self, trace_ids, location_id, location_dest_id) -> None:
        if not trace_ids:
            return
        rental_stock_move = self.env["stock.move"].create(
            {
                "product_id": self.product_id.id,
                "product_uom_qty": len(trace_ids),
                "product_uom_id": self.product_id.uom_id.id,
                "location_id": location_id.id,
                "location_dest_id": location_dest_id.id,
                "partner_id": self.partner_id.id,
                "sale_line_id": self.id,
            }
        )

        for trace_id in trace_ids:
            lot_quant = self.env["stock.quant"]._gather(
                self.product_id, location_id, trace_id
            )
            lot_quant = lot_quant.filtered(lambda quant: quant.quantity == 1)
            if not lot_quant:
                _debug.logic(
                    "rental_serial_quant_missing",
                    line=self,
                    lot=trace_id,
                    location=location_id,
                )
                raise ValidationError(
                    self.env._(
                        "No valid quant has been found in location %(location)s for serial number %(serial_number)s!",
                        location=location_id.name,
                        serial_number=trace_id.name,
                    )
                )
            ml = self.env["stock.move.line"].create(
                rental_stock_move._prepare_move_line_vals(reserved_quant=lot_quant)
            )
            ml["quantity"] = 1

        _debug.lifecycle(
            "rental_serials_moved",
            line=self,
            lots=len(trace_ids),
            move=rental_stock_move,
            to=location_dest_id,
        )
        rental_stock_move.picked = True
        rental_stock_move._action_done()

    def _return_serials(self, trace_ids, location_id, location_dest_id) -> None:
        if not trace_ids:
            return
        rental_stock_move = self.env["stock.move"].search(
            [
                ("sale_line_id", "=", self.id),
                ("location_id", "=", location_id.id),
                ("location_dest_id", "=", location_dest_id.id),
            ]
        )
        for ml in rental_stock_move.mapped("move_line_ids"):
            if ml.trace_id.id in trace_ids:
                ml.quantity = 0.0

        rental_stock_move.product_uom_qty -= len(trace_ids)

    def _move_qty(self, qty, location_id, location_dest_id) -> None:
        rental_stock_move = self.env["stock.move"].create(
            {
                "product_id": self.product_id.id,
                "product_uom_qty": qty,
                "product_uom_id": self.product_id.uom_id.id,
                "location_id": location_id.id,
                "location_dest_id": location_dest_id.id,
                "partner_id": self.partner_id.id,
                "sale_line_id": self.id,
                "state": "confirmed",
            }
        )
        rental_stock_moves = rental_stock_move._set_rental_sm_qty()
        for move in rental_stock_moves:
            move._action_assign()
            move.quantity = move.product_uom_qty
            move.picked = True
        rental_stock_moves._action_done()

    def _return_qty(self, qty, location_id, location_dest_id) -> bool:
        rental_stock_move = self.env["stock.move"].search(
            [
                ("sale_line_id", "=", self.id),
                ("location_id", "=", location_id.id),
                ("location_dest_id", "=", location_dest_id.id),
            ],
            order="date desc",
        )

        for ml in rental_stock_move.mapped("move_line_ids"):
            qty -= ml.quantity
            ml.quantity = 0.0 if qty > 0.0 else -qty

            if qty <= 0.0:
                return True

        return qty <= 0.0

    def web_gantt_write(self, vals):
        result = super().web_gantt_write(vals)

        order_lines = self.order_id.line_ids
        storable_products = order_lines.product_id.filtered("is_storable")
        if not storable_products:
            return result

        stock_quants = dict(
            self.env["stock.quant"]._read_group(
                Domain(
                    [
                        ("product_id", "in", storable_products.ids),
                        ("location_id.usage", "=", "internal"),
                    ]
                ),
                groupby=["product_id"],
                aggregates=["quantity:sum"],
            )
        )
        reserved_quants = dict(
            self.env["sale.order.line"]._read_group(
                Domain(
                    [
                        ("product_id", "in", storable_products.ids),
                        ("is_rental", "=", True),
                        ("state", "=", "done"),
                        ("start_date", "<=", self.return_date),
                        ("return_date", ">=", self.start_date),
                    ]
                ),
                groupby=["product_id"],
                aggregates=["product_qty:sum"],
            )
        )
        for product in stock_quants.keys() | reserved_quants.keys():
            if stock_quants.get(product, 0) < reserved_quants.get(product, 0):
                result["notifications"].append(
                    {
                        "type": "warning",
                        "message": self.env._(
                            "Not enough %(product)s in stock.\n"
                            "%(reserved_qty)s reserved but only %(stock_qty)s in stock.",
                            product=product.display_name,
                            reserved_qty=reserved_quants.get(product, 0),
                            stock_qty=stock_quants.get(product, 0),
                        ),
                        "code": "stock_inconsistency",
                    }
                )

        if not self._are_rental_pickings_enabled():
            return result

        order_reserved_lots = order_lines.reserved_trace_ids
        lots_reserved_in_different_order = (
            self.env["sale.order.line"]
            .search_fetch(
                Domain(
                    [
                        ("reserved_trace_ids", "in", order_reserved_lots.ids),
                        ("id", "not in", order_lines.ids),
                        ("is_rental", "=", True),
                        ("start_date", "<=", self.return_date),
                        ("return_date", ">=", self.start_date),
                    ]
                ),
                ["reserved_trace_ids"],
            )
            .reserved_trace_ids
            & order_reserved_lots
        )
        if lots_reserved_in_different_order:
            result["notifications"].append(
                {
                    "type": "warning",
                    "message": self.env._(
                        "%(lots)s %(are)s reserved on multiple order lines",
                        lots=", ".join(
                            lots_reserved_in_different_order.mapped("display_name")
                        ),
                        are="are"
                        if len(lots_reserved_in_different_order) > 1
                        else "is",
                    ),
                    "code": "lot_overbooking",
                }
            )

        if vals.get("reserved_trace_ids") and self.product_qty > len(
            self.reserved_trace_ids
        ):
            view = self.env.ref(
                "sale_stock_renting.sale_order_line_form_lot_allocation"
            )
            result["notifications"].append(
                {
                    "type": "warning",
                    "message": self.env._(
                        "The number of reserved lots is less than the quantity required for this order"
                        " line. Please allocate additional lots."
                    ),
                    "code": "insufficient_reserved_lots",
                }
            )
            result["actions"].append(
                {
                    "name": self.env._("Lot Allocation"),
                    "type": "ir.actions.act_window",
                    "res_model": "sale.order.line",
                    "views": [(view.id, "form")],
                    "res_id": self.id,
                    "target": "new",
                }
            )

        return result

    @api.constrains("product_id")
    def _check_rental_stock_product(self) -> None:
        for line in self.filtered("is_rental"):
            moves = line.move_ids.filtered(lambda m: m.state != "cancel")
            if moves and moves.mapped("product_id") != line.product_id:
                _debug.logic("rental_product_change_refused", line=line, moves=moves)
                raise ValidationError(
                    self.env._(
                        "You cannot change the product of lines linked to stock moves."
                    )
                )

    def _create_procurements(self, product_qty, procurement_uom, values) -> list:
        if self.is_rental and self._are_rental_pickings_enabled():
            values["route_ids"] = values.get("route_ids") or self.env.ref(
                "sale_stock_renting.route_rental"
            )
            delivery_values = {
                **values,
                "date_planned": self.order_id.rental_start_date,
                "date_deadline": self.order_id.rental_start_date,
            }
            return_values = {
                **values,
                "date_planned": self.order_id.rental_return_date,
                "date_deadline": self.order_id.rental_return_date,
            }
            return [
                self.env["stock.rule"].Procurement(
                    self.product_id,
                    product_qty,
                    procurement_uom,
                    self.order_id.company_id.rental_loc_id,
                    self.product_id.display_name,
                    self.order_id.name,
                    self.order_id.company_id,
                    delivery_values,
                ),
                self.env["stock.rule"].Procurement(
                    self.product_id,
                    product_qty,
                    procurement_uom,
                    self.order_id.warehouse_id.lot_stock_id,
                    self.product_id.display_name,
                    self.order_id.name,
                    self.order_id.company_id,
                    return_values,
                ),
            ]
        return super()._create_procurements(product_qty, procurement_uom, values)

    def _action_launch_stock_rule(self, **kwargs):
        if not self or self._are_rental_pickings_enabled():
            super()._action_launch_stock_rule(**kwargs)
            returns = self.move_ids.filtered(
                lambda m: m.location_id == self.company_id.rental_loc_id
            )
            picks = self.move_ids.filtered(
                lambda m: m.location_id == self.warehouse_id.lot_stock_id
            )
            moves_by_order_line = defaultdict(
                lambda: {
                    "picks": self.env["stock.move"],
                    "returns": self.env["stock.move"],
                }
            )
            for move in picks:
                if move.state in ("done", "cancel"):
                    continue
                moves_by_order_line[move.sale_line_id]["picks"] |= move
            for move in returns:
                if move.state in ("done", "cancel"):
                    continue
                moves_by_order_line[move.sale_line_id]["returns"] |= move
            returns._unreserve()
            for moves in moves_by_order_line.values():
                moves["returns"].write(
                    {
                        "move_orig_ids": [
                            Command.link(pick.id) for pick in moves["picks"]
                        ],
                        "procure_method": "make_to_order",
                    }
                )
                moves["returns"].picking_id.return_id = moves["picks"].picking_id
            returns._recompute_state()
        else:
            other_lines = self.filtered(lambda sol: not sol.is_rental)
            super(SaleOrderLine, other_lines)._action_launch_stock_rule(**kwargs)

    def _get_procurement_qty(self, previous_product_qty=False):
        if not self.is_rental or not self._are_rental_pickings_enabled():
            return super()._get_procurement_qty(previous_product_qty)
        moves = self._get_transferable_moves()
        scheduled_returns = moves.filtered(
            lambda move: (
                move.location_id == self.company_id.rental_loc_id
                and not move.origin_returned_move_id
            )
        )
        return self._get_pipeline_qty(moves - scheduled_returns)

    def _get_stock_moves_outgoing_incoming(self):
        outgoing_moves, incoming_moves = super()._get_stock_moves_outgoing_incoming()
        if self.is_rental and self._are_rental_pickings_enabled():
            for move in self.move_ids.filtered(
                lambda r: (
                    r.state != "cancel"
                    and r.location_dest_usage != "inventory"
                    and self.product_id == r.product_id
                )
            ):
                if move.location_dest_id == self.company_id.rental_loc_id:
                    outgoing_moves |= move
                elif move.location_id == self.company_id.rental_loc_id:
                    incoming_moves |= move

        return outgoing_moves, incoming_moves

    def _compute_qty_transferred(self):
        super()._compute_qty_transferred()

        if not self._are_rental_pickings_enabled():
            return

        for line in self:
            if line.is_rental and line.product_id.type == "consu":
                qty = 0.0
                outgoing_moves, _incoming_moves = (
                    line._get_stock_moves_outgoing_incoming()
                )
                for move in outgoing_moves:
                    if move.state != "done":
                        continue
                    qty += move.product_uom_id._get_quantity_in_unit(
                        move.quantity, line.product_uom_id, rounding_method="HALF-UP"
                    )
                line.qty_transferred = qty

    def _prepare_qty_transferred(self):
        delivered_qties = super()._prepare_qty_transferred()

        if not self._are_rental_pickings_enabled():
            return delivered_qties

        for line in self:
            if line.is_rental and line.product_id.type == "consu":
                qty = 0.0
                outgoing_moves, _incoming_moves = (
                    line._get_stock_moves_outgoing_incoming()
                )
                for move in outgoing_moves:
                    if move.state != "done":
                        continue
                    qty += move.product_uom_id._get_quantity_in_unit(
                        move.quantity, line.product_uom_id, rounding_method="HALF-UP"
                    )
                delivered_qties[line] = qty
        return delivered_qties

    @api.depends("pickedup_trace_ids", "returned_trace_ids", "reserved_trace_ids")
    def _compute_unavailable_lots(self) -> None:
        for line in self:
            line.unavailable_trace_ids = (
                line.reserved_trace_ids | line.pickedup_trace_ids
            ) - line.returned_trace_ids

    @api.depends("start_date", "is_rental")
    def _compute_reservation_begin(self) -> None:
        lines = self.filtered(lambda line: line.is_rental)
        for line in lines:
            padding_timedelta_before = timedelta(hours=line.product_id.preparation_time)
            line.reservation_begin = (
                line.start_date and line.start_date - padding_timedelta_before
            )
        (self - lines).reservation_begin = None

    def _get_rented_quantities(self, mandatory_dates):
        if not self:
            return defaultdict(float), sorted(set(mandatory_dates))
        self.product_id.check_singleton()
        rented_quantities = defaultdict(float)
        now = fields.Datetime.now()
        for so_line in self.filtered("is_rental"):
            rented_quantities[so_line.reservation_begin] += so_line.product_qty
            rented_quantities[so_line.return_date] -= so_line.product_qty
            if so_line.reservation_begin > now and so_line.qty_transferred > 0:
                rented_quantities[now] += so_line.qty_transferred
                rented_quantities[so_line.reservation_begin] -= so_line.qty_transferred
            if so_line.return_date > now and so_line.qty_returned > 0:
                rented_quantities[now] -= so_line.qty_returned
                rented_quantities[so_line.return_date] += so_line.qty_returned

        key_dates = sorted(set(rented_quantities.keys()) | set(mandatory_dates))
        return rented_quantities, key_dates

    @api.model
    def _are_rental_pickings_enabled(self):
        return self.env["res.groups"]._is_feature_enabled(
            "sale_stock_renting.group_rental_stock_picking"
        )

    def _prepare_procurement_vals(self):
        values = super()._prepare_procurement_vals()
        if self._are_rental_pickings_enabled() and self.is_rental:
            values["to_refund"] = False
        return values
