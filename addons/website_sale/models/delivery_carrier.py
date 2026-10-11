from typing import TYPE_CHECKING, cast

from odoo import api, fields, models

if TYPE_CHECKING:
    from odoo.addons.base.models.uom_uom import UomUom
    from odoo.addons.product.models.product_template import ProductTemplate


class DeliveryCarrier(models.Model):
    _name = "delivery.carrier"
    _inherit = ["delivery.carrier", "mixin.website.published.multi"]

    website_description = fields.Text(
        related="product_id.description_sale",
        string="Description for Online Quotations",
        readonly=False,
    )

    @api.model
    def _get_pickup_radius_uom(self) -> UomUom:
        product_template = cast("ProductTemplate", self.env["product.template"])
        return cast(
            "UomUom",
            product_template._get_uom_from_setting("distance"),
        )
