from odoo import fields, models


class SaleOrderLine(models.Model):
    _name = "sale.order.line"
    _inherit = ["mixin.order.line.agreement", "sale.order.line"]

    agreement_line_id = fields.Many2one(comodel_name="sale.agreement.line")

    def _get_agreed_price(self):
        self.check_singleton()
        agreement_line = self._find_agreement_line()
        if not agreement_line.product_id:
            return None
        order = self.order_id
        unit = self.product_uom_id or self.product_id.uom_id
        qty = unit._get_quantity_in_unit(
            self.product_qty,
            agreement_line.product_uom_id,
            round=False,
            raise_if_failure=False,
        )
        price = agreement_line.product_uom_id._get_price_in_unit(
            agreement_line._get_price_for_qty(qty), unit
        )
        return agreement_line.agreement_id.currency_id._convert(
            price,
            order.currency_id,
            order.company_id,
            self._get_date_order(),
            round=False,
        )

    def _get_auto_discount(self, pricelist_price=False, base_price=False):
        agreement_line = self._find_agreement_line()
        if agreement_line.product_category_id:
            return agreement_line.discount
        return super()._get_auto_discount(pricelist_price, base_price)

    def _get_pricelist_price(self):
        agreed = self._get_agreed_price()
        return super()._get_pricelist_price() if agreed is None else agreed

    def _get_pricelist_price_before_discount(self):
        agreed = self._get_agreed_price()
        if agreed is None:
            return super()._get_pricelist_price_before_discount()
        return agreed
