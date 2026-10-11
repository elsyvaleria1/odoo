from odoo import api, models
from odoo.fields import Domain


class SaleOrderTemplateLine(models.Model):
    _inherit = "sale.order.template.line"

    @api.model
    def _domain_product_id(self):
        return Domain.OR([super()._domain_product_id(), [("rent_ok", "=", True)]])
