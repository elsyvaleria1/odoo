from odoo import api, fields, models
from odoo.fields import Domain


class SpreadsheetCellThread(models.Model):
    _inherit = "spreadsheet.cell.thread"

    dashboard_id = fields.Many2one(
        comodel_name="spreadsheet.dashboard",
        readonly=True,
        ondelete="cascade",
    )

    def _get_spreadsheet_record(self):
        return super()._get_spreadsheet_record() or self.dashboard_id

    @api.model
    def _access_guard(self, operation):
        # a thread follows the spreadsheet it is written on
        return super()._access_guard(operation) & (
            Domain("dashboard_id", "=", False)
            | Domain("dashboard_id", "access", "read")
        )
