from odoo import api, models
from odoo.fields import Domain


class StockMove(models.Model):
    _inherit = "stock.move"

    def _get_locations_rental_picking_compatible(self):
        rental_loc = self.company_id.rental_loc_id
        locations = rental_loc | rental_loc.location_id
        if (
            rental_loc
            and self.sale_line_id.order_id.is_rental_order
            and self.location_dest_id in locations
            and self.env["res.groups"]._is_feature_enabled(
                "sale_stock_renting.group_rental_stock_picking"
            )
        ):
            return locations
        return self.env["stock.location"]

    def _get_picking_destination(self):
        if self._get_locations_rental_picking_compatible():
            return self.company_id.rental_loc_id.location_id
        return super()._get_picking_destination()

    def _get_domain_picking_for_assignation(self):
        """This modifies the picking search domain for rental moves.

        Modify the picking search domain to make sure that rental moves are on the
        same picking as sale moves in case of hybrid rental orders, while still making
        sure that modifying the SO line quantity is propagated to stock moves correctly.
        """
        domain = super()._get_domain_picking_for_assignation()
        locations = self._get_locations_rental_picking_compatible()
        if locations:
            domain = (
                Domain(domain)
                .optimize(self.env["stock.picking"])
                .map_conditions(
                    lambda cond: (
                        Domain(
                            "location_dest_id",
                            "in",
                            set(locations.ids).union(
                                [cond.value] if cond.operator == "=" else cond.value
                            ),
                        )
                        if cond.field_expr == "location_dest_id"
                        and cond.operator in ("=", "in")
                        else cond
                    )
                )
            )
        return domain

    def _prepare_procurement_vals(self):
        res = super()._prepare_procurement_vals()
        if (
            self.sale_line_id._are_rental_pickings_enabled()
            and self.sale_line_id.is_rental
            and self.sale_line_id.is_mto
        ):
            res["route_ids"] = self.rule_id.route_id
        return res

    def _prepare_merge_moves_distinct_fields(self):
        distinct_fields = super()._prepare_merge_moves_distinct_fields()
        if any(
            sale_order.is_rental_order for sale_order in self.reference_ids.sale_ids
        ):
            distinct_fields.remove("origin_returned_move_id")
            distinct_fields.remove("procure_method")
        return distinct_fields

    def _action_assign(self):
        """Assign the trace_id present on the SO line to the stock move lines for rental orders."""
        super()._action_assign()

        moves_by_product = self.grouped("product_id")
        for product in self.product_id:
            if product.tracking != "serial":
                continue
            moves = moves_by_product[product]
            sale_lines = self.env["sale.order.line"]
            for move in moves:
                sale_lines |= move._get_sale_order_lines()
            if sale_lines.reserved_trace_ids:
                free_reserved_lots = (
                    sale_lines.reserved_trace_ids - moves.move_line_ids.trace_id
                )
                to_assign_move_lines = moves.move_line_ids.filtered_domain(
                    [("trace_id", "not in", sale_lines.reserved_trace_ids.ids)]
                )
                for line, lot in zip(
                    to_assign_move_lines, free_reserved_lots, strict=False
                ):
                    quant = lot.quant_ids.filtered_domain(
                        [
                            ("location_id", "=", line.location_id.id),
                            ("quantity", "=", 1),
                            ("reserved_quantity", "=", 0),
                        ]
                    )
                    if quant:
                        line.trace_id = lot

    def _action_done(self, cancel_backorder=False):
        """Correctly set the qty_transferred and qty_returned of rental order lines when using pickings."""
        res = super()._action_done(cancel_backorder=cancel_backorder)
        if self.env["res.groups"]._is_feature_enabled(
            "sale_stock_renting.group_rental_stock_picking"
        ):
            for move in self:
                if move.state != "done":
                    continue
                if (
                    not move.sale_line_id.is_rental
                    or move.product_id != move.sale_line_id.product_id
                ):
                    continue
                if move.location_id == move.company_id.rental_loc_id:
                    current_qty_returned = move.product_uom_id._get_quantity_in_unit(
                        move.quantity,
                        move.sale_line_id.product_uom_id,
                        rounding_method="HALF-UP",
                    )
                    if move.sale_line_id.order_id.is_late:
                        move.sale_line_id._create_delay_line(current_qty_returned)
                    move.sale_line_id.qty_returned += current_qty_returned
                if move.picked and move.sale_line_id.tracking == "serial":
                    # Synchronize the reserved lots with the picked lots.
                    # Ensure reserved lots include all picked lots and any extra reserved lots.
                    sol = move.sale_line_id
                    qty_to_keep_reserved = max(
                        int(sol.product_qty),
                        len(move.trace_ids),
                        len(sol.reserved_trace_ids),
                    )
                    sol.reserved_trace_ids = (move.trace_ids | sol.reserved_trace_ids)[
                        :qty_to_keep_reserved
                    ]
        return res

    def _compute_location_dest_id(self):
        moves_to_super = self.env["stock.move"]
        for move in self:
            if (
                move.location_dest_id
                and move.location_final_id
                and move.sale_line_id
                and not move.sale_line_id.is_rental
                and move.sale_line_id.order_id.is_rental_order
                and move.picking_type_id.code == "outgoing"
                and move.location_final_id._is_child_of(move.location_dest_id)
            ):
                move.location_dest_id = move.location_final_id
            else:
                moves_to_super |= move

        if moves_to_super:
            super(StockMove, moves_to_super)._compute_location_dest_id()

    @api.depends("sale_line_id.order_id.name")
    def _compute_reference(self) -> None:
        moves_with_reference = set()
        for move in self:
            if move.sale_line_id.is_rental and not move.picking_id:
                move.reference = self.env._(
                    "Rental move: %(order)s", order=move.sale_line_id.order_id.name
                )
                moves_with_reference.add(move.id)
        super(
            StockMove, self - self.env["stock.move"].browse(moves_with_reference)
        )._compute_reference()

    def _set_rental_sm_qty(self):
        self.check_singleton()
        return self

    def _is_incoming(self) -> bool:
        if (
            self.company_id.rental_loc_id == self.location_id
            and self.location_dest_id.usage == "internal"
        ):
            return True

        return super()._is_incoming()
