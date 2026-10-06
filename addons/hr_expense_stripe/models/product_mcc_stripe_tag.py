from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


# https://docs.stripe.com/connect/setting-mcc#list
class ProductMCCSTripeTag(models.Model):
    _name = "product.mcc.stripe.tag"
    _inherit = ["mixin.color"]
    _description = "Stripe MCC Tag"
    _order = "code"
    _color_default_indices = tuple(range(10))

    name = fields.Char(
        translate=True,
        required=True,
    )
    stripe_name = fields.Char(
        readonly=True,
        required=True,
    )
    code = fields.Char(
        size=4,
        index="btree",
        copy=False,
        readonly=True,
        required=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Expense Category to use",
        company_dependent=True,
        domain=[("can_be_expensed", "=", True), ("standard_price", "=", 0)],
    )
    product_name = fields.Char(
        related="product_id.name",
        string="Product Name",
    )
    color = fields.Integer(
        string="Color Index",
        default=lambda self: self._default_color(),
        store=True,
    )

    _constraint_code_unique = models.Constraint(
        definition="unique(code)",
        message="The code of the MCC tag must be unique!",
    )

    @api.constrains("product_id")
    def _check_no_cost(self) -> None:
        price_precision = self.env["decimal.precision"].get_precision("Product Price")
        for product in self.product_id:
            if round(product.standard_price, int(price_precision)) != 0:
                raise ValidationError(
                    self.env._(
                        "To be used by Expense cards, the product '%(name)s' must have a cost of 0.00",
                        name=product.name,
                    )
                )

    def write(self, vals):
        if ("code" in vals or "stripe_name" in vals) and not self.has_access("create"):
            raise UserError(
                self.env._(
                    "Only administrators can change the code or the stripe technical name of a MCC."
                )
            )
        return super().write(vals)
