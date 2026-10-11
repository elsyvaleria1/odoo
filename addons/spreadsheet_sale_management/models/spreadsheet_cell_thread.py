from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import frozendict


class SpreadsheetCellThread(models.Model):
    _inherit = "spreadsheet.cell.thread"
    _access_anchors = frozendict(
        {
            "sale_order_spreadsheet_order_user_or_unset": models.Anchor(
                "sale_order_spreadsheet_id.order_id.user_id", kind="owner", shared=True
            ),
        }
    )

    sale_order_spreadsheet_id = fields.Many2one(
        comodel_name="sale.order.spreadsheet",
        readonly=True,
        ondelete="cascade",
    )

    def _get_spreadsheet_record(self):
        return super()._get_spreadsheet_record() or self.sale_order_spreadsheet_id

    @api.model
    def _access_guard(self, operation):
        return super()._access_guard(operation) & (
            Domain("sale_order_spreadsheet_id", "=", False)
            | Domain("sale_order_spreadsheet_id", "access", "read")
        )
