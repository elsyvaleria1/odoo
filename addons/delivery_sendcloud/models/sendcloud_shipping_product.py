from odoo import api, fields, models


class SendcloudShippingProduct(models.Model):
    _name = "sendcloud.shipping.product"

    _description = "Choose from the available sendcloud shipping products"

    name = fields.Char(
        string="Shipping Product",
        readonly=True,
        required=True,
    )
    sendcloud_code = fields.Char(
        string="Sendcloud Product Identifier",
        readonly=True,
        required=True,
    )
    carrier = fields.Char(
        string="Shipping Carrier",
        readonly=True,
    )
    min_weight = fields.Integer(
        string="Minimum Weight",
        readonly=True,
    )
    max_weight = fields.Integer(
        string="Maximum Weight",
        readonly=True,
    )
    functionalities = fields.Json(
        string="Available Functionalities",
        readonly=True,
    )
    can_customize_functionalities = fields.Boolean(
        compute="_compute_can_customize_functionalities",
        store=True,
    )
    has_multicollo = fields.Boolean(
        compute="_compute_has_multicollo",
        store=True,
    )

    @api.depends("functionalities")
    def _compute_can_customize_functionalities(self) -> None:
        self.can_customize_functionalities = False
        for sc_product in self:
            if sc_product.functionalities.get("customizable"):
                sc_product.can_customize_functionalities = True

    @api.depends("functionalities")
    def _compute_has_multicollo(self) -> None:
        self.has_multicollo = False
        for sc_product in self:
            if "Multicollo" in sc_product.functionalities.get("bool_func", []):
                sc_product.has_multicollo = True
