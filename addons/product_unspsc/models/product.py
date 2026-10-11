from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Domain


class ProductTemplate(models.Model):
    _inherit = "product.template"

    unspsc_code_id = fields.Many2one(
        comodel_name="product.unspsc.code",
        string="UNSPSC Category",
        domain=[("applies_to", "=", "product")],
        help="The UNSPSC code related to this product.  Used for edi in Colombia, Peru, Mexico and Denmark",
    )

    @api.constrains("unspsc_code_id")
    def _check_unspsc_code_id(self) -> None:
        for template in self:
            if (
                template.unspsc_code_id
                and template.unspsc_code_id.applies_to != "product"
            ):
                raise ValidationError(
                    self.env._(
                        "The UNSPSC code %(code)s applies to UoM, not to products.",
                        code=template.unspsc_code_id.display_name,
                    )
                )


class UomUom(models.Model):
    _inherit = "uom.uom"

    unspsc_code_id = fields.Many2one(
        comodel_name="product.unspsc.code",
        string="UNSPSC Category",
        domain=[("applies_to", "=", "uom")],
        help="The UNSPSC code related to this UoM. ",
    )

    @api.constrains("unspsc_code_id")
    def _check_unspsc_code_id(self) -> None:
        for uom in self:
            if uom.unspsc_code_id and uom.unspsc_code_id.applies_to != "uom":
                raise ValidationError(
                    self.env._(
                        "The UNSPSC code %(code)s applies to products, not to UoM.",
                        code=uom.unspsc_code_id.display_name,
                    )
                )


class ProductUnspscCode(models.Model):

    _name = "product.unspsc.code"
    _description = "Product and UOM Codes from UNSPSC"
    _rec_names_search = ["name", "code"]

    _code_uniq = models.Constraint("unique(code)", "This UNSPSC code already exists.")

    code = fields.Char(required=True)
    name = fields.Char(
        translate=True,
        required=True,
    )
    applies_to = fields.Selection(
        selection=[
            ("product", "Product"),
            ("uom", "UoM"),
        ],
        required=True,
        help="Indicate if this code could be used in products or in UoM",
    )
    active = fields.Boolean(default=True)

    @api.depends("code")
    def _compute_display_name(self):
        for prod in self:
            prod.display_name = f"{prod.code} {prod.name or ''}"

    @api.model
    def _search_display_name(self, operator, value):
        if operator == "in":
            return Domain(
                "code", "in", [(v or "").split(" ")[0] for v in value]
            ) | Domain("name", "in", value)
        if operator in Domain.NEGATIVE_OPERATORS:
            return NotImplemented
        if isinstance(value, str) and value:
            code_value = value.split(" ")[0]
            return Domain("code", operator, code_value) | Domain(
                "name", operator, value
            )
        if operator == "=":
            operator = "in"
            value = [value]
        return super()._search_display_name(operator, value)


class ProductProduct(models.Model):
    _inherit = "product.product"

    def _get_import_product_classification_specs(self):
        return super()._get_import_product_classification_specs() + [
            {
                "value_key": "unspsc_code",
                "field": "unspsc_code_id",
                "comodel": "product.unspsc.code",
                "code_field": "code",
            },
        ]
