from typing import Any

from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)

TRANSFER_BUCKETS = ("ready", "late", "waiting")


class HomeTile(models.AbstractModel):
    _inherit = "home.tile"

    _TRANSFER_TYPES_SHOWN = 6

    @api.model
    def _get_tile_types(self) -> dict[str, dict[str, Any]]:
        return {
            **super()._get_tile_types(),
            "transfers": {
                "name": self.env._("Transfers"),
                "sizes": ["1x1", "2x1"],
                "model": "stock.picking",
            },
        }

    @api.model
    def _get_tile_transfers_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        picking_types = self.env["stock.picking.type"].search([])
        rows = [
            {
                "id": picking_type.id,
                "name": picking_type.display_name,
                **{
                    bucket: picking_type[f"count_picking_{bucket}"]
                    for bucket in TRANSFER_BUCKETS
                },
            }
            for picking_type in picking_types
        ]
        totals = {
            bucket: sum(row[bucket] for row in rows) for bucket in TRANSFER_BUCKETS
        }
        busiest = sorted(
            (row for row in rows if row["ready"] or row["late"]),
            key=lambda row: (-row["late"], -row["ready"], row["name"]),
        )
        _debug.logic("transfers_tile", types=len(rows), **totals)
        return {**totals, "types": busiest[: self._TRANSFER_TYPES_SHOWN]}
