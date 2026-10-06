from odoo import api, fields, models
from odoo.fields import Domain
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)


class SpreadsheetCellThread(models.Model):
    _inherit = "spreadsheet.cell.thread"
    _access_anchors = frozendict(
        {
            "owner": "template_id.create_uid",
        }
    )

    document_id = fields.Many2one(
        comodel_name="document.document",
        readonly=True,
        ondelete="cascade",
    )
    template_id = fields.Many2one(
        comodel_name="spreadsheet.template",
        readonly=True,
        ondelete="cascade",
    )

    def _get_spreadsheet_record(self):
        if _debug.logic.enabled:
            _debug.logic(
                "cell_thread_owner",
                thread=self,
                document=self.document_id,
                template=self.template_id,
            )
        return super()._get_spreadsheet_record() or self.document_id or self.template_id

    @api.model
    def _access_guard(self, operation):
        # a thread follows the spreadsheet it is written on
        return (
            super()._access_guard(operation)
            & (
                Domain("document_id", "=", False)
                | Domain("document_id", "access", "read")
            )
            & (
                Domain("template_id", "=", False)
                | Domain("template_id", "access", "read")
            )
        )
