from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    documents_hr_payslips_tags = fields.Many2many(
        comodel_name="document.tag",
        related="company_id.documents_hr_payslips_tags",
        string="Payslip",
        readonly=False,
    )
