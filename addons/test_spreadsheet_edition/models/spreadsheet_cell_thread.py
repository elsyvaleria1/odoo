from odoo import api, fields, models
from odoo.fields import Domain


class SpreadsheetCellThread(models.Model):
    _inherit = "spreadsheet.cell.thread"

    dummy_id = fields.Many2one(
        comodel_name="spreadsheet.test",
        readonly=True,
        ondelete="cascade",
    )

    def _get_spreadsheet_record(self):
        return super()._get_spreadsheet_record() or self.dummy_id

    @api.model
    def _access_guard(self, operation):
        return super()._access_guard(operation) & (
            Domain("dummy_id", "=", False) | Domain("dummy_id", "access", "read")
        )
