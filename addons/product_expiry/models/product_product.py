from odoo import api, fields, models
from odoo.fields import Domain


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _prepare_quantities_vals(self, filters, location_domains=None):
        return super(
            ProductProduct,
            self.with_context(with_expiration=fields.Datetime.now()),
        )._prepare_quantities_vals(filters, location_domains=location_domains)

    @api.depends_context("with_expiration", "fresh_qty_forecast")
    @api.depends("stock_quant_ids.removal_date")
    def _compute_quantities(self):
        return super()._compute_quantities()

    def _get_expired_quant_domain_at_date(self, domain_quant, to_date):
        if not self.env.context.get("with_expiration"):
            return None
        max_date = (
            to_date
            if to_date and self.env.context.get("fresh_qty_forecast")
            else self.env.context["with_expiration"]
        )
        return domain_quant & Domain([("removal_date", "<=", max_date)])

    qty_free = fields.Float(
        help="Available quantity (computed as Quantity On Hand "
        "- reserved quantity - quantity to remove)\n"
        "In a context with a single Stock Location, this includes "
        "goods stored in this location, or any of its children.\n"
        "In a context with a single Warehouse, this includes "
        "goods stored in the Stock Location of this Warehouse, or any "
        "of its children.\n"
        "Otherwise, this includes goods stored in any Stock Location "
        "with 'internal' type."
    )

    qty_available_virtual = fields.Float(
        help="Forecast quantity (computed as Quantity On Hand "
        "- Outgoing + Incoming - Quantity to Remove)\n"
        "In a context with a single Stock Location, this includes "
        "goods stored in this location, or any of its children.\n"
        "In a context with a single Warehouse, this includes "
        "goods stored in the Stock Location of this Warehouse, or any "
        "of its children.\n"
        "Otherwise, this includes goods stored in any Stock Location "
        "with 'internal' type."
    )


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.depends_context("with_expiration", "fresh_qty_forecast")
    def _compute_quantities(self):
        return super()._compute_quantities()
