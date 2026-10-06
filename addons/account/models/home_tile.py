from typing import Any

from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HomeTile(models.AbstractModel):
    _inherit = "home.tile"

    _JOURNALS_SHOWN = 6

    @api.model
    def _get_tile_types(self) -> dict[str, dict[str, Any]]:
        return {
            **super()._get_tile_types(),
            "journals": {
                "name": self.env._("Accounting"),
                "sizes": ["1x1", "2x1"],
                "model": "account.move",
                "menu": "account.menu_board_journal_1",
            },
        }

    @api.model
    def _get_tile_journals_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        journals = self.env["account.journal"].search(
            [("show_on_dashboard", "=", True)]
        )
        counts = journals._get_attention_counts()
        buckets = ("to_reconcile", "to_validate", "late")
        rows = [
            {
                "id": journal.id,
                "name": journal.display_name,
                "type": journal.type,
                **counts[journal.id],
            }
            for journal in journals
        ]
        busiest = sorted(
            (row for row in rows if any(row[bucket] for bucket in buckets)),
            key=lambda row: tuple(-row[bucket] for bucket in buckets) + (row["name"],),
        )
        _debug.logic("journals_tile", journals=len(rows))
        return {
            **{bucket: sum(row[bucket] for row in rows) for bucket in buckets},
            "journals": busiest[: self._JOURNALS_SHOWN],
        }
