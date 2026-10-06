from odoo import models


class ReportPaperformat(models.Model):
    _name = "report.paperformat"
    _inherit = ["mixin.studio", "report.paperformat"]
