from odoo import fields, models


class WizardProductProductViewRoute(models.TransientModel):
    _inherit = "wizard.product.product.view.route"

    so_route_ids = fields.Many2many(
        comodel_name="stock.route",
        string="Apply specific routes",
        domain="[('sale_selectable', '=', True)]",
        help="Choose to apply SO lines specific routes.",
    )

    def _prepare_report_data(self):
        data = super()._prepare_report_data()
        data["so_route_ids"] = self.so_route_ids.ids
        return data
