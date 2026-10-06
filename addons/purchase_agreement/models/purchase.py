from odoo import fields, models


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["mixin.order.agreement", "purchase.order"]

    agreement_id = fields.Many2one(
        comodel_name="purchase.agreement",
        string="Agreement",
        index="btree_not_null",
        copy=False,
    )
    agreement_type = fields.Selection(related="agreement_id.agreement_type")

    def _prepare_grouped_data(self, rfq):
        match_fields = super()._prepare_grouped_data(rfq)
        return match_fields + (rfq.agreement_id.id,)


class PurchaseOrderLine(models.Model):
    _name = "purchase.order.line"
    _inherit = ["mixin.order.line.agreement", "purchase.order.line"]

    agreement_line_id = fields.Many2one(comodel_name="purchase.agreement.line")

    def _get_line_description_from_product(self, product_lang):
        name = super()._get_line_description_from_product(product_lang)
        return self._find_agreement_line()._add_description_variants(name)
