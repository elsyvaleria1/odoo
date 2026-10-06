from odoo import fields, models


class SaleOrderTemplateLine(models.Model):
    _name = "sale.order.template.line"
    _inherit = ["mixin.order.template.line"]
    _description = "Quotation Template Line"

    template_id = fields.Many2one(
        comodel_name="sale.order.template",
        string="Quotation Template Reference",
    )
    parent_id = fields.Many2one(comodel_name="sale.order.template.line")
    is_optional = fields.Boolean(
        string="Optional Line",
        default=False,
        copy=True,
    )

    def _get_product_description(self):
        self.check_singleton()
        return self.product_id.get_product_multiline_description_sale()

    def _prepare_order_line_values(self):
        values = super()._prepare_order_line_values()
        values["is_optional"] = self.is_optional
        return values
