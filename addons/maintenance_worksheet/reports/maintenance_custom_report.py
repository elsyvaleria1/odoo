from odoo import api, models


class ReportMaintenance_WorksheetMaintenance_Worksheet(models.AbstractModel):
    _name = "report.maintenance_worksheet.maintenance_worksheet"
    _description = "Maintenance Order Worksheet Custom Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["maintenance.order"].browse(docids)
        docs.check_access("read")
        docs = docs.sudo()
        worksheet_map = {}
        for order in docs:
            if order.worksheet_template_id:
                x_model = order.worksheet_template_id.model_id.model
                worksheet = self.env[x_model].search(
                    [("x_maintenance_order_id", "=", order.id)]
                )
                worksheet_map[order.id] = worksheet
        return {
            "doc_model": "maintenance.order",
            "doc_ids": docids,
            "docs": docs,
            "worksheet_map": worksheet_map,
        }
