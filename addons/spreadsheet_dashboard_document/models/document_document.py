from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class DocumentsDocument(models.Model):
    _inherit = "document.document"

    def _get_spreadsheet_metadata(self, access_token=None):
        data = super()._get_spreadsheet_metadata(access_token)
        if _debug.logic.enabled:
            _debug.logic(
                "dashboard_metadata",
                document=self,
                can_add=self.env["spreadsheet.dashboard"].has_access("create"),
            )
        return dict(
            data,
            can_add_to_dashboard=self.env["spreadsheet.dashboard"].has_access("create"),
        )
