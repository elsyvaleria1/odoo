from odoo import api, models


class ReportQuality_ControlQuality_Worksheet(models.AbstractModel):
    _name = "report.quality_control.quality_worksheet"
    _description = "Quality Worksheet Report"

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.env["quality.check"].browse(docids)
        docs.check_access("read")
        docs = docs.sudo()

        return {
            "doc_ids": docids,
            "doc_model": "quality.check",
            "docs": docs,
        }


class ReportQuality_ControlQuality_Worksheet_Internal(models.AbstractModel):
    _name = "report.quality_control.quality_worksheet_internal"
    _description = "Quality Worksheet Internal Report"
    _inherit = ["report.quality_control.quality_worksheet"]
