from odoo import api, fields, models
from odoo.tools import format_list


class ProductTemplate(models.Model):
    _inherit = "product.template"

    weight_capacity = fields.Float(string="Max Weight")
    volume_capacity = fields.Float(string="Max Volume")


class ProductProduct(models.Model):
    _inherit = "product.product"

    @api.depends_context("show_load_capacity")
    def _compute_display_name(self):
        super()._compute_display_name()
        if not self.env.context.get("show_load_capacity"):
            return
        for product in self:
            capacities = []
            if product.weight_capacity:
                capacities.append(
                    self.env._(
                        "%(weight_capacity)s %(weight_uom)s",
                        weight_capacity=product.weight_capacity,
                        weight_uom=product.weight_uom_name,
                    )
                )
            if product.volume_capacity:
                capacities.append(
                    self.env._(
                        "%(volume_capacity)s %(volume_uom)s",
                        volume_capacity=product.volume_capacity,
                        volume_uom=product.volume_uom_name,
                    )
                )
            if capacities:
                product.display_name = self.env._(
                    "%(display_name)s (%(load_capacity)s)",
                    display_name=product.display_name,
                    load_capacity=format_list(self.env, capacities, "unit-short"),
                )

    def _trip_weight(self, quantity):
        """What ``quantity`` of this product weighs, in its unit, without packaging.

        :param float quantity: quantity in the product's unit of measure
        :rtype: float
        """
        self.check_singleton()
        return quantity * self.weight
