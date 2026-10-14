import logging
from collections import defaultdict

from odoo import SUPERUSER_ID, api
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        "UPDATE stock_move_line SET reservation_trace_id = trace_id"
        " WHERE trace_id IS NOT NULL"
    )
    env = api.Environment(cr, SUPERUSER_ID, {})
    MoveLine = env["stock.move.line"]
    Quant = env["stock.quant"]
    outstanding = MoveLine._get_domain_outstanding_reservation(
        include_picked=True
    ) & Domain("product_id.is_storable", "=", True)
    lines = MoveLine.search(
        outstanding, order="id desc"
    )._filtered_holding_reservation()
    lot_lines = lines.filtered("trace_id")
    if not lot_lines:
        return

    def place(record):
        return (
            record.product_id,
            record.location_id,
            record.package_id,
            record.owner_id,
        )

    held_by_lot_key = defaultdict(float)
    held_untracked = defaultdict(float)
    for line in lines:
        if line.trace_id:
            held_by_lot_key[place(line), line.trace_id] += line.quantity_product_uom
        else:
            held_untracked[place(line)] += line.quantity_product_uom
    capacity_by_lot_key = defaultdict(float)
    untracked_surplus = defaultdict(float)
    for quant in Quant.search(
        [
            ("product_id", "in", lot_lines.product_id.ids),
            ("location_id", "in", lot_lines.location_id.ids),
        ]
    ):
        if quant.trace_id:
            capacity_by_lot_key[place(quant), quant.trace_id] += max(
                quant.quantity, quant.reserved_quantity
            )
        else:
            untracked_surplus[place(quant)] += quant.reserved_quantity
    for key, held in held_untracked.items():
        untracked_surplus[key] -= held

    untracked = MoveLine
    for line in lot_lines:
        key = (place(line), line.trace_id)
        uom = line.product_id.uom_id
        shortfall = held_by_lot_key[key] - capacity_by_lot_key[key]
        surplus = untracked_surplus[place(line)]
        if (
            uom._compare_aggregate(shortfall, 0) <= 0
            or uom._compare_aggregate(surplus, line.quantity_product_uom) < 0
        ):
            continue
        untracked |= line
        held_by_lot_key[key] -= line.quantity_product_uom
        untracked_surplus[place(line)] -= line.quantity_product_uom
    if untracked:
        _logger.info(
            "%s lot move lines are reserved on untracked stock; keyed accordingly.",
            len(untracked),
        )
        untracked.write({"reservation_trace_id": False})
    Quant._sync_reserved_quantities(
        products=lot_lines.product_id, locations=lot_lines.location_id
    )
