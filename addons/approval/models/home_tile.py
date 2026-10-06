from typing import Any

from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class HomeTile(models.AbstractModel):
    _inherit = "home.tile"

    _APPROVALS_SHOWN = 5

    @api.model
    def _get_tile_types(self) -> dict[str, dict[str, Any]]:
        return {
            **super()._get_tile_types(),
            "approvals": {
                "name": self.env._("Approvals"),
                "sizes": ["1x1", "2x1"],
                "model": "approval.request",
            },
        }

    @api.model
    def _get_tile_approvals_data(self, settings: dict[str, Any]) -> dict[str, Any]:
        Request = self.env["approval.request"]
        domain = [("is_pending_my_review", "=", True)]
        requests = Request.search(
            domain, limit=self._APPROVALS_SHOWN, order="approval_deadline, id"
        )
        count = Request.search_count(domain)
        overdue = Request.search_count([*domain, ("is_overdue", "=", True)])
        _debug.logic("approvals_tile", count=count, overdue=overdue)
        return {
            "count": count,
            "overdue": overdue,
            "requests": [
                {
                    "id": request.id,
                    "name": request.name,
                    "category": request.category_id.display_name,
                    "owner": request.request_owner_id.display_name,
                    "deadline": request.approval_deadline,
                    "overdue": request.is_overdue,
                }
                for request in requests
            ],
        }
