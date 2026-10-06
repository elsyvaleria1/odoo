from odoo import api, fields, models


class AppointmentType(models.Model):
    _inherit = "appointment.type"

    @api.model
    def _product_id_domain(self) -> list:
        return [
            ("type", "=", "service"),
            ("sale_ok", "=", True),
            (
                "service_tracking",
                "not in",
                self.env["product.template"]._service_tracking_blacklist(),
            ),
        ]

    has_payment_step = fields.Boolean(
        string="Up-front Payment",
        help="Require visitors to pay to confirm their booking",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Booking Product",
        compute="_compute_product_id",
        store=True,
        readonly=False,
        domain=_product_id_domain,
        tracking=True,
    )
    product_currency_id = fields.Many2one(related="product_id.currency_id")
    product_lst_price = fields.Float(related="product_id.lst_price")

    _check_product_and_payment_step = models.Constraint(
        "CHECK(has_payment_step IS NULL OR NOT has_payment_step OR product_id IS NOT NULL)",
        "Activating the payment step requires a product",
    )

    @api.depends("has_payment_step")
    def _compute_product_id(self) -> None:
        needs_product = self.filtered("has_payment_step")
        (self - needs_product).product_id = False
        if not needs_product:
            return
        default_product = self.env.ref(
            "appointment_account_payment.default_booking_product",
            raise_if_not_found=False,
        )
        if not default_product:
            return
        needs_product.filtered(
            lambda app: not app.product_id
        ).product_id = default_product
