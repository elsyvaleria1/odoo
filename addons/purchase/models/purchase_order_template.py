from odoo import fields, models

from odoo.addons.trade.tools import PURCHASE


class PurchaseOrderTemplate(models.Model):
    _name = "purchase.order.template"
    _inherit = ["mixin.order.template"]
    _description = "Request for Quotation Template"
    _direction = PURCHASE

    name = fields.Char(string="RFQ Template")
    line_ids = fields.One2many(comodel_name="purchase.order.template.line")


class PurchaseOrderTemplateLine(models.Model):
    _name = "purchase.order.template.line"
    _inherit = ["mixin.order.template.line"]
    _description = "Request for Quotation Template Line"

    template_id = fields.Many2one(comodel_name="purchase.order.template")
    parent_id = fields.Many2one(comodel_name="purchase.order.template.line")

    def _get_product_description(self):
        self.check_singleton()
        product = self.product_id
        name = product.display_name
        if product.description_purchase:
            name += "\n" + product.description_purchase
        return name
