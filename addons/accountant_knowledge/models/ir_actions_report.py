from odoo import models


class IrActionsReport(models.Model):
    _inherit = "ir.actions.report"

    def _render_html_to_pdf(self, *args, **kwargs):
        if self.env.context.get("page_format") == "audit_report":
            kwargs["specific_paperformat_args"] = None
        return super()._render_html_to_pdf(*args, **kwargs)

    def get_paperformat(self):
        if self.env.context.get("page_format") == "audit_report":
            return self.env["report.paperformat"].new(
                {
                    "name": "A4 - Audit Report",
                    "format": "A4",
                    "orientation": "Portrait",
                    "margin_top": 12,
                    "margin_bottom": 12,
                    "margin_left": 8,
                    "margin_right": 8,
                    "css_margins": False,
                }
            )
        return super().get_paperformat()
