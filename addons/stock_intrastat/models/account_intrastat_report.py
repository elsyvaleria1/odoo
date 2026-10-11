from odoo import api, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockIntrastatReportHandler(models.AbstractModel):
    _name = "stock.intrastat.report.handler"
    _inherit = ["account.intrastat.report.handler"]
    _description = "Intrastat Report Custom Handler (Stock)"

    @api.model
    def _update_missing_values(self, vals_list):
        _debug.pipeline("intrastat_missing_values", count=len(vals_list))
        vals_list = super()._update_missing_values(vals_list)

        invoice_ids = [vals["invoice_id"] for vals in vals_list]

        warehouses = (
            self.env["stock.warehouse"].with_context(active_test=False).search([])
        )
        regions = warehouses.mapped("intrastat_region_id")

        if not regions:
            return vals_list

        if len(regions) == 1 and all(wh.intrastat_region_id for wh in warehouses):
            for val in vals_list:
                val["region_code"] = regions.code
            return vals_list

        for invoice, vals in zip(
            self.env["account.move"].browse(invoice_ids), vals_list, strict=True
        ):
            stock_moves = invoice._stock_account_get_last_step_stock_moves()
            if stock_moves:
                warehouse = (
                    stock_moves[0].warehouse_id
                    or stock_moves[0].picking_id.picking_type_id.warehouse_id
                )
                if warehouse.intrastat_region_id.code:
                    vals["region_code"] = warehouse.intrastat_region_id.code
        return vals_list
