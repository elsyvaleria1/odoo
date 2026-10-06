from odoo import api, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.onchange("project_id")
    def _onchange_project(self) -> None:
        if self.project_id.worksheet_template_id:
            self.worksheet_template_id = self.project_id.worksheet_template_id
