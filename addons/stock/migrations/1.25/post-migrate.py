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
    lot_lines = MoveLine.search(
        MoveLine._get_domain_outstanding_reservation(include_picked=True)
        & Domain("trace_id", "!=", False)
        & Domain("product_id.is_storable", "=", True),
        order="id desc",
    )
    lines_by_key = defaultdict(lambda: MoveLine)
    for line in lot_lines:
        lines_by_key[line._get_reservation_key()] |= line
    reserved_by_key = {
        (product, location, lot, package, owner): reserved
        for product, location, lot, package, owner, reserved in env[
            "stock.quant"
        ]._read_group(
            [
                ("trace_id", "in", lot_lines.trace_id.ids),
                ("location_id", "in", lot_lines.location_id.ids),
            ],
            ["product_id", "location_id", "trace_id", "package_id", "owner_id"],
            ["reserved_quantity:sum"],
        )
    }
    untracked = MoveLine
    for key, lines in lines_by_key.items():
        uom = key[0].uom_id
        shortfall = sum(lines.mapped("quantity_product_uom")) - reserved_by_key.get(
            key, 0.0
        )
        for line in lines:
            if uom._compare_aggregate(shortfall, 0) <= 0:
                break
            untracked |= line
            shortfall -= line.quantity_product_uom
    if untracked:
        _logger.info(
            "%s lot move lines are reserved on untracked stock; keyed accordingly.",
            len(untracked),
        )
        untracked.write({"reservation_trace_id": False})
    env["stock.quant"]._sync_reserved_quantities(
        products=lot_lines.product_id, locations=lot_lines.location_id
    )
