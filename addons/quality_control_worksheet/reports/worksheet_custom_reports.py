from odoo import api, models


class ReportQuality_ControlQuality_Worksheet(models.AbstractModel):
    _inherit = "report.quality_control.quality_worksheet"

    @api.model
    def _get_report_values(self, docids, data=None):
        pdf_data = super()._get_report_values(docids, data)

        worksheet_map = {}
        for check in pdf_data.get("docs"):
            if check.worksheet_template_id:
                x_model = check.worksheet_template_id.model_id.model
                worksheet = self.env[x_model].search(
                    [("x_quality_check_id", "=", check.id)],
                    limit=1,
                    order="create_date DESC",
                )
                worksheet_map[check.id] = worksheet

        pdf_data["worksheet_map"] = worksheet_map
        return pdf_data
