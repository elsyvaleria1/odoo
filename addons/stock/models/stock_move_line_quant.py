from collections import defaultdict
from typing import Self

from markupsafe import Markup

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command, Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import OrderedSet

from ..const import INVENTORY_REFERENCE_REVERTED, LOCKED_QUANTS_CACHE_KEY
from ..tools.quantity import get_faithful_quantity
from .stock_move_line import (
    _KEEP,
    DEST_QUANT_FIELDS,
    RENDERED_KEYS,
    RESERVATION_KEY_FIELDS,
    RESTOCK_TRIGGER_FIELDS,
)

_debug = DebugLog(__name__)


class StockMoveLineQuant(models.Model):
    _inherit = "stock.move.line"

    def _update_quants(
        self, *, quantity=None, reverse=False, in_date=False, release_reserved=False
    ) -> tuple:
        self.check_singleton()
        qty = self.quantity_product_uom if quantity is None else quantity
        if reverse:
            from_loc, to_loc, from_package = (
                self.location_dest_id,
                self.location_id,
                self.result_package_id,
            )
        else:
            from_loc, to_loc, from_package = (
                self.location_id,
                self.location_dest_id,
                self.package_id,
            )
        _debug.pipeline(
            "update_quants",
            line=self.id,
            qty=qty,
            source=from_loc.id,
            destination=to_loc.id,
            reverse=reverse,
            release=release_reserved,
        )
        available_qty, in_date = self._update_quant_at_location(
            -qty,
            from_loc,
            package=from_package,
            in_date=in_date,
            reserved_delta=-qty if release_reserved and not reverse else None,
        )
        self._update_quant_at_location(
            qty,
            to_loc,
            package=self.package_id if reverse else self.result_package_id,
            in_date=in_date,
        )
        _debug.logic("update_quants_available", line=self.id, available=available_qty)
        return available_qty, in_date

    def _get_lines_to_requant(self, vals, updates) -> tuple:
        restock_ids = OrderedSet()
        adjust_ids = OrderedSet()
        for ml in self:
            if ml.state != "done" or not ml.product_id.is_storable:
                continue
            changed = ml._get_changed_write_fields(vals, updates)
            if not changed:
                continue
            if changed.intersection(RESTOCK_TRIGGER_FIELDS):
                restock_ids.add(ml.id)
            else:
                adjust_ids.add(ml.id)
        return self.browse(restock_ids), self.browse(adjust_ids)

    def _filtered_keeping_destination(self, vals, updates) -> Self:
        return self.filtered(
            lambda ml: (
                not ml._get_changed_write_fields(vals, updates).intersection(
                    DEST_QUANT_FIELDS
                )
            )
        )

    def _revert_quant_moves(self, keeping_destination=None):
        keep = set((keeping_destination or self.browse())._ids)
        if _debug.pipeline.enabled and self:
            _debug.pipeline("revert_quant_moves", move_lines=self, keep=sorted(keep))
        in_dates = {}
        for ml in self.with_context(quants_cache=self._get_quants_cache()):
            _available_qty, in_date = ml._update_quants(reverse=True)
            if ml.id in keep:
                in_dates[ml.id] = in_date
        if self.move_id:
            self.move_id._check_quantity()
        return in_dates

    def _update_quants_again(self, in_dates=None) -> None:
        in_dates = in_dates or {}
        notes = defaultdict(list)
        for ml in self.with_context(quants_cache=self._get_quants_cache()):
            ml._update_quants_and_reservations(
                in_date=in_dates.get(ml.id, False), notes=notes
            )
        self._post_consumed_pick_notes(notes)

    def _get_quantity_deltas(self, vals, updates) -> dict:
        return {
            ml.id: ml._get_new_quantity_product_uom(vals, updates)
            - ml.quantity_product_uom
            for ml in self
        }

    def _update_quants_by_delta(self, deltas) -> None:
        if _debug.pipeline.enabled and self:
            _debug.pipeline("quants_by_delta", deltas=deltas)
        notes = defaultdict(list)
        for ml in self.with_context(quants_cache=self._get_quants_cache()):
            ml._update_quants_and_reservations(quantity=deltas[ml.id], notes=notes)
        self._post_consumed_pick_notes(notes)
        if self.move_id:
            self.move_id._check_quantity()

    def _log_quant_corrections(self, vals) -> None:
        for picking, lines in self.grouped("picking_id").items():
            if not picking:
                continue
            corrections = []
            for ml in lines:
                data = ml._get_logged_relations(ml, vals)
                if RENDERED_KEYS & set(data):
                    corrections.append({"move": ml, "vals": data})
            if not corrections:
                continue
            picking.message_post_with_source(
                "stock.track_move_lines_template",
                render_values={"corrections": corrections},
                subtype_xmlid="mail.mt_note",
            )

    def _get_quants_cache(self):
        if not self:
            return None
        return self.env["stock.quant"]._get_quants_by_products_locations(
            self.product_id,
            self.location_id | self.location_dest_id,
            lot_scope=self.trace_id,
        )

    def _update_quants_and_reservations(
        self,
        *,
        quantity=None,
        in_date=False,
        release_reserved=False,
        ml_ids_to_ignore=None,
        notes=None,
    ) -> None:
        self.check_singleton()
        available_qty, _in_date = self._update_quants(
            quantity=quantity, in_date=in_date, release_reserved=release_reserved
        )
        if self.product_id.uom_id._compare_aggregate(available_qty, 0) < 0:
            _debug.logic("source_negative", line=self.id, available=available_qty)
            freed_notes = self._free_reservation(
                abs(available_qty), ml_ids_to_ignore=ml_ids_to_ignore
            )
            if notes is None:
                self._post_consumed_pick_notes(freed_notes)
            else:
                for document, lines in freed_notes.items():
                    notes[document].extend(lines)

    def _get_reservation_key(self, overrides=None):
        self.check_singleton()
        overrides = overrides or {}
        return tuple(overrides.get(name, self[name]) for name in RESERVATION_KEY_FIELDS)

    @api.model
    def _get_domain_outstanding_reservation(self, include_picked=False):
        domain = Domain(
            [
                ("state", "not in", ["done", "cancel"]),
                ("quantity_product_uom", ">", 0.0),
            ]
        )
        if include_picked:
            return domain
        return domain & Domain("picked", "=", False)

    def _update_quant_reservations(self, deltas) -> None:
        if len(deltas) > 1 and self.env.context.get("quants_cache") is None:
            quants_cache = self._get_quants_cache()
            self = self.with_context(quants_cache=quants_cache)
            keyed = self.env["stock.quant"].concat(
                *(
                    quants_cache[product.id, location.id, lot.id, package.id, owner.id]
                    for product, location, lot, package, owner in deltas
                )
            )
            held = self.env.cr.cache.setdefault(LOCKED_QUANTS_CACHE_KEY, set())
            held.update(keyed.filtered(lambda q: q.id not in held)._try_lock().ids)
        for (product, location, lot, package, owner), quantity in deltas.items():
            if product.uom_id._is_zero_aggregate(quantity):
                continue
            _debug.lifecycle(
                "reservation_delta",
                quantity=quantity,
                product=product.id,
                location=location.id,
                lot=lot.id,
                package=package.id,
            )
            self.env["stock.quant"]._update_reserved_quantity(
                product,
                location,
                quantity,
                trace_id=lot,
                package_id=package,
                owner_id=owner,
            )

    def _reserve_quants(self):
        return self._update_reservations_by_sign(1)

    def _release_quants(self):
        return self._update_reservations_by_sign(-1)

    def _update_reservations_by_sign(self, sign):
        holding = self._filtered_holding_reservation()
        deltas = defaultdict(float)
        for ml in holding:
            deltas[ml._get_reservation_key()] += sign * ml.quantity_product_uom
        holding._update_quant_reservations(deltas)
        return holding

    @_debug.perf.timed
    def _free_reservation(self, quantity, ml_ids_to_ignore=None) -> dict:
        self.check_singleton()
        product, location = self.product_id, self.location_id
        ml_ids_to_ignore = OrderedSet(ml_ids_to_ignore or ()) | OrderedSet(self.ids)

        if self._is_reservation_bypass_required(location):
            return {}
        _debug.pipeline(
            "free_reservation",
            line=self.id,
            quantity=quantity,
            product=product.id,
            location=location.id,
        )
        self = self.sudo().with_context(quants_cache=None)

        move_to_reassign = self.env["stock.move"]
        to_unlink_candidate_ids = set()
        product_uom = product.uom_id
        for candidate in self._get_outdated_candidates(ml_ids_to_ignore):
            move_to_reassign |= candidate.move_id
            if (
                product_uom._compare_aggregate(candidate.quantity_product_uom, quantity)
                <= 0
            ):
                quantity -= candidate.quantity_product_uom
                to_unlink_candidate_ids.add(candidate.id)
                if product_uom._is_zero_aggregate(quantity):
                    break
            else:
                kept = candidate.quantity_product_uom - quantity
                kept_in_line_uom = get_faithful_quantity(
                    product_uom, kept, candidate.product_uom_id
                )
                if kept_in_line_uom is None:
                    _debug.logic(
                        "free_reservation_line_to_product_uom",
                        line=candidate.id,
                        kept=kept,
                        line_uom=candidate.product_uom_id.name,
                    )
                    candidate.write(
                        {"product_uom_id": product_uom.id, "quantity": kept}
                    )
                else:
                    candidate.quantity = kept_in_line_uom
                break

        move_line_to_unlink = self.env["stock.move.line"].browse(
            to_unlink_candidate_ids
        )
        moves_to_sever = move_line_to_unlink.move_id.filtered(
            lambda m: not (m.move_line_ids - move_line_to_unlink)
        )
        _debug.logic(
            "free_reservation_plan",
            unlink=move_line_to_unlink,
            sever=moves_to_sever,
            reassign=move_to_reassign,
            unfreed=quantity,
        )
        moves_to_sever.write(
            {"procure_method": "make_to_stock", "move_orig_ids": [Command.clear()]}
        )
        (move_to_reassign - moves_to_sever).filtered(
            lambda m: m.procure_method != "make_to_stock"
        ).procure_method = "make_to_stock"
        consumed_picks = move_line_to_unlink.filtered("picked")
        notes = self._prepare_consumed_pick_notes(consumed_picks)
        move_line_to_unlink.unlink()
        moves_to_sever.filtered("picked").picked = False
        refill = (move_to_reassign - moves_to_sever).filtered("picked")
        move_to_reassign[::-1].with_context(
            reserve_picked_move_ids=refill.ids
        )._action_assign()
        return notes

    @api.model
    def _post_consumed_pick_notes(self, notes) -> None:
        for document, lines in notes.items():
            document.message_post(
                body=Markup("<br/>").join(lines), subtype_xmlid="mail.mt_note"
            )

    def _get_consumer_label(self) -> str:
        self.check_singleton()
        if self.move_id.is_inventory:
            return self.env._("an inventory adjustment")
        return self.reference or self.move_id.display_name

    def _prepare_consumed_pick_notes(self, consumed_picks) -> dict:
        self.check_singleton()
        notes = defaultdict(list)
        for line in consumed_picks:
            document = line.move_id._get_handling_document()
            if not document:
                continue
            notes[document].append(
                self.env._(
                    "%(trace)s left %(location)s with %(consumer)s: the line that"
                    " had picked it is removed.",
                    trace=line.trace_id.display_name,
                    location=line.location_id.display_name,
                    consumer=self._get_consumer_label(),
                )
            )
        _debug.logic(
            "consumed_pick_notes",
            line=self.id,
            picks=consumed_picks,
            documents=len(notes),
        )
        return notes

    def _get_outdated_candidates(self, ml_ids_to_ignore) -> Self:
        self.check_singleton()

        def get_candidate_rank(candidate):
            date = candidate.picking_id.date_planned or candidate.move_id.date
            return (
                candidate.picking_id != self.move_id.picking_id,
                candidate.picked,
                -date.timestamp() if date else 0,
                -candidate.id,
            )

        domain = self._get_domain_outstanding_reservation(
            include_picked=bool(self.trace_id) and self.product_id.tracking == "serial"
        )
        domain &= Domain(
            [(name, "=", self[name].id) for name in RESERVATION_KEY_FIELDS]
        )
        domain &= Domain("id", "not in", tuple(ml_ids_to_ignore))
        return self.search(domain).sorted(get_candidate_rank)

    def _filtered_holding_reservation(self) -> Self:
        return self.filtered(
            lambda ml: (
                not ml.product_uom_id._is_zero_stored(
                    ml.quantity_product_uom, ml.product_id.uom_id
                )
                and not ml._is_reservation_bypass_required(ml.location_id)
            )
        )

    def _reserve_new_move_lines(self) -> None:
        to_reserve = self.filtered(lambda ml: ml.state != "done")
        reserved = to_reserve._reserve_quants()
        if _debug.logic.enabled and to_reserve:
            _debug.logic("new_lines_reserved", reserved=reserved, to_reserve=to_reserve)
        (
            reserved.move_id
            | to_reserve.move_id.filtered(lambda move: move.state != "draft")
        )._recompute_state()

    def _sync_quant_reservation(self, vals, updates):
        moves_to_recompute_state = self.env["stock.move"]
        if not (
            (set(updates) - {"result_package_id", "location_dest_id"})
            or "quantity" in vals
        ):
            return moves_to_recompute_state
        deltas = defaultdict(float)
        for ml in self:
            if not ml.product_id.is_storable or ml.state == "done":
                continue
            if "quantity" in vals or "product_uom_id" in vals:
                new_reserved_qty = ml._get_new_quantity_product_uom(vals, updates)
                if ml.product_id.uom_id.compare(new_reserved_qty, 0) < 0:
                    raise UserError(self._get_negative_quantity_message())
            else:
                new_reserved_qty = ml.quantity_product_uom

            if not ml.product_uom_id._is_zero_stored(
                ml.quantity_product_uom, ml.product_id.uom_id
            ) and not ml._is_reservation_bypass_required(ml.location_id):
                deltas[ml._get_reservation_key()] -= ml.quantity_product_uom

            new_location = updates.get("location_id", ml.location_id)
            if not ml._is_reservation_bypass_required(new_location):
                deltas[ml._get_reservation_key(updates)] += new_reserved_qty

            if (
                "quantity" in vals
                and ml.product_uom_id.compare(vals["quantity"], ml.quantity)
            ) or "product_uom_id" in vals:
                moves_to_recompute_state |= ml.move_id

        _debug.logic(
            "quant_reservation_sync",
            move_lines=self,
            deltas=len(deltas),
            recompute=moves_to_recompute_state,
        )
        self._update_quant_reservations(deltas)
        return moves_to_recompute_state

    def _update_quant_at_location(
        self,
        quantity,
        location,
        in_date=False,
        reserved_delta=None,
        lot=_KEEP,
        package=_KEEP,
        owner=_KEEP,
    ) -> tuple:
        lot = self.trace_id if lot is _KEEP else lot
        package = self.package_id if package is _KEEP else package
        owner = self.owner_id if owner is _KEEP else owner
        available_qty = 0
        if not self.product_id.is_storable or self.product_uom_id._is_zero_stored(
            quantity, self.product_id.uom_id
        ):
            return 0, False
        if reserved_delta and self._is_reservation_bypass_required(location):
            reserved_delta = None
        available_qty, in_date = self.env["stock.quant"]._update_available_quantity(
            self.product_id,
            location,
            quantity,
            reserved_quantity=reserved_delta or False,
            trace_id=lot,
            package_id=package,
            owner_id=owner,
            in_date=in_date,
        )
        if lot and self.product_id.uom_id._compare_aggregate(available_qty, 0) < 0:
            _debug.logic(
                "lot_short_compensate",
                line=self.id,
                lot=lot.id,
                available=available_qty,
                location=location.id,
            )
            self._compensate_lot_shortfall(
                location, lot, package, owner, abs(quantity), in_date
            )
        return available_qty, in_date

    def _compensate_lot_shortfall(
        self, location, lot, package, owner, cap, in_date
    ) -> None:
        Quant = self.env["stock.quant"]
        shortfall = Quant._get_on_hand_shortfall(
            self.product_id, location, lot, package_id=package, owner_id=owner
        )
        if not shortfall:
            return
        untracked_qty = Quant._get_available_quantity(
            self.product_id,
            location,
            trace_id=False,
            package_id=package,
            owner_id=owner,
            strict=True,
        )
        if not untracked_qty:
            return
        taken_from_untracked_qty = min(untracked_qty, shortfall, cap)
        _debug.logic(
            "lot_shortfall_compensated",
            shortfall=shortfall,
            untracked=untracked_qty,
            cap=cap,
            taken=taken_from_untracked_qty,
        )
        Quant._update_available_quantity(
            self.product_id,
            location,
            -taken_from_untracked_qty,
            trace_id=False,
            package_id=package,
            owner_id=owner,
            in_date=in_date,
        )
        Quant._update_available_quantity(
            self.product_id,
            location,
            taken_from_untracked_qty,
            trace_id=lot,
            package_id=package,
            owner_id=owner,
            in_date=in_date,
        )

    def _is_reservation_bypass_required(self, location) -> bool:
        self.check_singleton()
        if self.move_id:
            return self.move_id._is_reservation_bypass_required(location)
        return (
            not self.product_id.is_storable or location.is_reservation_bypass_required()
        )

    def _resolve_serial_sources(self) -> None:
        lines = self.filtered(
            lambda ml: (
                ml.trace_id
                and ml.product_id.tracking == "serial"
                and ml.location_id.usage in ("internal", "transit")
                and not ml._is_reservation_bypass_required(ml.location_id)
            )
        )
        if not lines:
            return
        quants = (
            self.env["stock.quant"]
            ._with_quant_upkeep()
            .search(
                [
                    ("product_id", "in", lines.product_id.ids),
                    ("trace_id", "in", lines.trace_id.ids),
                    ("location_id", "child_of", lines.location_id.ids),
                    ("quantity", ">", 0),
                ]
            )
        )
        quants_by_trace = quants.grouped("trace_id")
        notes = defaultdict(list)
        line_ids_by_source = defaultdict(list)
        for line in lines:
            under = quants_by_trace.get(line.trace_id, quants.browse()).filtered(
                lambda quant, line=line: quant.location_id.parent_path.startswith(
                    line.location_id.parent_path
                )
            )
            if not under or any(
                quant.location_id == line.location_id
                and quant.package_id == line.package_id
                and quant.owner_id == line.owner_id
                for quant in under
            ):
                continue
            if len(under) > 1:
                _debug.logic("serial_source_ambiguous", line=line.id, quants=under)
                continue
            _debug.logic(
                "serial_source_resolved",
                line=line.id,
                trace=line.trace_id.id,
                stated=line.location_id.id,
                found=under.location_id.id,
            )
            if document := line.move_id._get_handling_document():
                notes[document].append(
                    self.env._(
                        "%(trace)s was taken from %(found)s, where it is, not from"
                        " %(stated)s.",
                        trace=line.trace_id.display_name,
                        found=under.location_id.display_name,
                        stated=line.location_id.display_name,
                    )
                )
            line_ids_by_source[
                under.location_id, under.package_id, under.owner_id
            ].append(line.id)
        for (location, package, owner), line_ids in line_ids_by_source.items():
            self.browse(line_ids).write(
                {
                    "location_id": location.id,
                    "package_id": package.id,
                    "owner_id": owner.id,
                }
            )
        self._post_consumed_pick_notes(notes)

    def _create_missing_quants(self, quants_cache) -> None:
        if quants_cache is None:
            return
        keys = OrderedSet()
        for ml in self:
            product = ml.product_id
            if not product.is_storable or ml.product_uom_id._is_zero_stored(
                ml.quantity_product_uom, product.uom_id
            ):
                continue
            keys.add((product, ml.location_id, ml.trace_id, ml.package_id, ml.owner_id))
            keys.add(
                (
                    product,
                    ml.location_dest_id,
                    ml.trace_id,
                    ml.result_package_id,
                    ml.owner_id,
                )
            )
        now = fields.Datetime.now()
        vals_list = [
            {
                "product_id": product.id,
                "location_id": location.id,
                "trace_id": lot.id,
                "package_id": package.id,
                "owner_id": owner.id,
                "quantity": 0.0,
                "in_date": now,
            }
            for product, location, lot, package, owner in keys
            if quants_cache.is_covering(product, location, lot)
            and not quants_cache[product.id, location.id, lot.id, package.id, owner.id]
        ]
        _debug.perf.count("quants_precreated", count=len(vals_list), lines=len(self))
        if vals_list:
            self.env["stock.quant"]._with_quant_upkeep().create(vals_list)

    @_debug.perf.timed
    def _update_quants_done(self) -> None:
        ml_ids_to_ignore = OrderedSet(self.ids)
        notes = defaultdict(list)
        quants_cache = self._get_quants_cache()
        self.with_context(quants_cache=quants_cache)._create_missing_quants(
            quants_cache
        )
        for ml in self.with_context(quants_cache=quants_cache):
            ml.with_context(bypass_entire_pack=True)._update_quants_and_reservations(
                release_reserved=True, ml_ids_to_ignore=ml_ids_to_ignore, notes=notes
            )
        self._post_consumed_pick_notes(notes)

    def get_move_line_quant_match(
        self, move_id, dirty_move_line_ids, dirty_quant_ids
    ) -> dict:
        move = self.env["stock.move"].browse(move_id)
        deleted_move_lines = move.move_line_ids - self
        dirty_move_lines = self.env["stock.move.line"].browse(dirty_move_line_ids)
        quants = []
        lines = []
        domain = Domain("id", "in", dirty_quant_ids) | Domain.OR(
            Domain(
                [(name, "=", move_line[name].id) for name in RESERVATION_KEY_FIELDS],
            )
            for move_line in dirty_move_lines | deleted_move_lines
        )
        if not domain.is_false():

            def get_reservation_key_ids(record):
                return tuple(record[name].id for name in RESERVATION_KEY_FIELDS)

            empty = self.env["stock.move.line"]
            dirty_by_key = defaultdict(lambda: empty)
            for move_line in dirty_move_lines:
                dirty_by_key[get_reservation_key_ids(move_line)] |= move_line
            deleted_by_key = defaultdict(lambda: empty)
            for move_line in deleted_move_lines:
                deleted_by_key[get_reservation_key_ids(move_line)] |= move_line

            for quant in self.env["stock.quant"].search(domain):
                key = get_reservation_key_ids(quant)
                dirty_lines = dirty_by_key.get(key, empty)
                deleted_lines = deleted_by_key.get(key, empty)
                quants.append(
                    {
                        "id": quant.id,
                        "available_quantity": quant.available_quantity
                        + sum(ml.quantity_product_uom for ml in deleted_lines),
                        "move_line_ids": dirty_lines.ids,
                    },
                )
                lines += [
                    {"id": ml.id, "quantity": ml.quantity, "quant_id": quant.id}
                    for ml in dirty_lines
                ]
        return {"quants": quants, "move_lines": lines}

    def action_revert_inventory(self) -> dict:
        revertable = self.filtered(
            lambda ml: ml.is_inventory and not ml.product_uom_id.is_zero(ml.quantity)
        )
        move_vals = [
            move_line._prepare_revert_inventory_move_vals()
            for move_line in revertable.with_context(inventory_mode=False)
        ]
        if not revertable:
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "type": "danger",
                    "message": self.env._(
                        "There are no inventory adjustments to revert."
                    ),
                },
            }
        _debug.pipeline("revert_inventory", move_lines=revertable, moves=len(move_vals))
        moves = (
            self.env["stock.move"].with_context(inventory_mode=False).create(move_vals)
        )
        moves._action_done()
        return {
            "name": self.env._("Reverted Moves"),
            "type": "ir.actions.act_window",
            "res_model": "stock.move.line",
            "view_mode": "list",
            "domain": [("id", "in", moves.move_line_ids.ids + self.ids)],
        }

    def _prepare_revert_inventory_move_vals(self) -> dict:
        self.check_singleton()
        return {
            "inventory_name": INVENTORY_REFERENCE_REVERTED % self.reference,
            "product_id": self.product_id.id,
            "product_uom_id": self.product_uom_id.id,
            "product_uom_qty": self.quantity,
            "company_id": self.company_id.id or self.env.company.id,
            "state": "confirmed",
            "location_id": self.location_dest_id.id,
            "location_dest_id": self.location_id.id,
            "is_inventory": True,
            "picked": True,
            "move_line_ids": [
                Command.create(
                    {
                        "product_id": self.product_id.id,
                        "product_uom_id": self.product_uom_id.id,
                        "quantity": self.quantity,
                        "location_id": self.location_dest_id.id,
                        "location_dest_id": self.location_id.id,
                        "company_id": self.company_id.id or self.env.company.id,
                        "trace_id": self.trace_id.id,
                        "package_id": self.result_package_id.id,
                        "result_package_id": self.package_id.id,
                        "owner_id": self.owner_id.id,
                    },
                )
            ],
        }
