from odoo import api, fields, models
from odoo.libs.numbers import float_repr

PRICER_RELATED_FIELDS = [
    "name",
    "lst_price",
    "list_price",
    "barcode",
    "weight",
    "to_weight",
    "stock",
    "taxes_id",
    "currency_id",
    "pricer_tag_ids",
    "pricer_store_id",
    "additional_product_tag_ids",
    "pricer_sale_pricelist_id",
    "on_sale_price",
]


class ProductProduct(models.Model):

    _inherit = "product.product"

    pricer_store_id = fields.Many2one(
        comodel_name="pricer.store",
        index="btree_not_null",
        help="This product will be linked to and displayed on the Pricer tags of the store selected here",
    )
    pricer_tag_ids = fields.One2many(
        comodel_name="pricer.tag",
        inverse_name="product_id",
        string="Pricer tags ids",
        help="This product will be linked to and displayed on the Pricer tags with ids listed here. It is recommended to use a barcode scanner",
    )

    pricer_product_to_create_or_update = fields.Boolean(default=False)

    pricer_display_price = fields.Char()

    pricer_sale_pricelist_id = fields.Many2one(
        comodel_name="product.pricelist",
        string="Pricer Sales Pricelist",
        domain=lambda self: [
            "&",
            ("item_ids.product_id", "=", self.id),
            "&",
            ("item_ids.min_quantity", "<=", 1),
            "|",
            ("item_ids.compute_price", "in", ["percentage", "fixed"]),
            ("item_ids.base", "in", ["list_price", "standard_price"]),
        ],
        help="This pricelist will be used to set sales on Pricer tags for this product",
    )

    on_sale_price = fields.Float(
        store=True,
        help="Price after setting a Pricer Sales Pricelist",
    )

    def compute_prices(self, on_sale=False):
        currency = self.currency_id
        price = self.on_sale_price if on_sale else self.lst_price
        taxes = self.taxes_id._filter_taxes_by_company(self.env.company)
        if not taxes:
            return float_repr(price, currency.decimal_places)
        else:
            res = taxes.compute_all(
                price, product=self, partner=self.env["res.partner"]
            )
            rounded_including = float_repr(
                res["total_included"], currency.decimal_places
            )
            rounded_excluding = float_repr(
                res["total_excluded"], currency.decimal_places
            )
            return (
                rounded_including
                if currency.compare_amounts(res["total_included"], price)
                else rounded_excluding
            )

    def _acquire_pricer_product_payload(self) -> dict:
        variants = [
            ",".join(record.product_attribute_value_id.mapped("name"))
            for record in self.product_template_variant_value_ids
            if record.price_extra and record.price_extra != 0
        ]
        variant = ",".join(variants)

        variants_tags = [
            ",".join(record.mapped("name"))
            for record in self.additional_product_tag_ids
        ]
        variant_tag = ",".join(variants_tags)

        self.pricer_display_price = self.compute_prices(
            on_sale=self.pricer_sale_pricelist_id
        )

        return {
            "itemId": str(self.id),
            "itemName": self.name,
            "price": self.pricer_display_price,
            "presentation": "PROMO"
            if self.pricer_sale_pricelist_id
            else "NORMAL",
            "properties": {
                "currency": self.currency_id.symbol,
                "barcode": self.barcode or "",
                "variant": variant or "",
                "variant_tag": variant_tag or "",
                "weight": self.weight or "",
                "stock": self.qty_available or "",
                "to_weight": self.to_weight or "",
                "old_price": self.compute_prices(on_sale=False),
            },
        }

    def write(self, vals):
        if any(val in PRICER_RELATED_FIELDS for val in vals):
            vals["pricer_product_to_create_or_update"] = True

        result = super().write(vals)
        if "pricer_store_id" in vals:
            self.pricer_tag_ids.pricer_product_to_link = True

        return result

    @api.onchange("pricer_sale_pricelist_id", "lst_price")
    def _onchange_compute_pricing(self) -> None:
        for product in self:
            if product.pricer_sale_pricelist_id:
                product._origin.lst_price = product.lst_price
                computed_price = product.pricer_sale_pricelist_id._get_product_price(
                    product._origin or product, quantity=1.0
                )
                product.on_sale_price = product._origin.on_sale_price = computed_price
            else:
                product.on_sale_price = 0.0
