from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.libs.debug_log import DebugLog

from odoo.addons.trade.tools import SALE

_debug = DebugLog(__name__)


class SaleOrderTemplate(models.Model):
    _name = "sale.order.template"
    _inherit = ["mixin.order.template"]
    _description = "Quotation Template"
    _direction = SALE

    name = fields.Char(string="Quotation Template")
    number_of_days = fields.Integer(
        string="Quotation Duration",
        help="Number of days for the validity date computation of the quotation",
    )
    mail_template_id = fields.Many2one(
        comodel_name="mail.template",
        string="Confirmation Mail",
        domain=[("model", "=", "sale.order")],
        help="This e-mail template will be sent on confirmation. Leave empty to send nothing.",
    )
    require_signature = fields.Boolean(
        string="Online Signature",
        compute="_compute_require_signature",
        store=True,
        readonly=False,
        help="Request a online signature to the customer in order to confirm orders automatically.",
    )
    require_payment = fields.Boolean(
        string="Online Payment",
        compute="_compute_require_payment",
        store=True,
        readonly=False,
        help="Request an online payment to the customer in order to confirm orders automatically.",
    )
    prepayment_percent = fields.Float(
        string="Prepayment percentage",
        compute="_compute_prepayment_percent",
        store=True,
        readonly=False,
        help="The percentage of the amount needed to be paid to confirm quotations.",
    )
    line_ids = fields.One2many(comodel_name="sale.order.template.line")
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Invoicing Journal",
        company_dependent=True,
        domain=[("type", "=", "sale")],
        check_company=True,
        help="If set, SO with this template will invoice in this journal; "
        "otherwise the sales journal with the lowest sequence is used.",
    )

    @api.depends("company_id")
    def _compute_require_signature(self) -> None:
        for order in self:
            order.require_signature = (
                order.company_id or order.env.company
            ).sale_config_id.portal_confirmation_sign

    @api.depends("company_id")
    def _compute_require_payment(self) -> None:
        for order in self:
            order.require_payment = (
                order.company_id or order.env.company
            ).sale_config_id.portal_confirmation_pay

    @api.depends("company_id", "require_payment")
    def _compute_prepayment_percent(self) -> None:
        for template in self:
            template.prepayment_percent = (
                template.company_id or template.env.company
            ).sale_config_id.prepayment_percent

    @api.onchange("prepayment_percent")
    def _onchange_prepayment_percent(self) -> None:
        for template in self:
            if not template.prepayment_percent:
                template.require_payment = False

    @api.constrains("prepayment_percent")
    def _check_prepayment_percent(self) -> None:
        for template in self:
            if template.require_payment and not (
                0 < template.prepayment_percent <= 1.0
            ):
                _debug.logic(
                    "template_prepayment_rejected",
                    template=template,
                    percent=template.prepayment_percent,
                )
                raise ValidationError(
                    self.env._("Prepayment percentage must be a valid percentage.")
                )

    def write(self, vals):
        if "active" in vals and not vals.get("active"):
            companies = (
                self.env["res.company"]
                .sudo()
                .search([("sale_config_id.sale_order_template_id", "in", self.ids)])
            )
            _debug.lifecycle(
                "company_default_template_cleared",
                templates=self,
                companies=companies,
            )
            companies.sale_config_id.sale_order_template_id = None
        return super().write(vals)

    @api.model
    def _demo_configure_template(self) -> None:
        demo_template = self.env.ref(
            "sale.sale_order_template_1", raise_if_not_found=False
        )
        if not demo_template or demo_template.line_ids:
            _debug.logic("demo_template_skipped", reason="missing_or_already_filled")
            return

        acoustic_bloc_screen_product = self.env.ref(
            "product.product_template_acoustic_bloc_screens"
        ).product_variant_id
        chair_protection_product = self.env.ref(
            "sale.product_product_1_product_template"
        ).product_variant_id
        demo_template.line_ids = [
            Command.create(
                {
                    "product_id": self.env.ref("product.consu_delivery_02").id,
                }
            ),
            Command.create(
                {
                    "product_id": self.env.ref("product.product_delivery_01").id,
                    "product_qty": 8,
                }
            ),
            Command.create(
                {
                    "product_id": acoustic_bloc_screen_product.id,
                }
            ),
            Command.create(
                {
                    "product_id": chair_protection_product.id,
                    "product_qty": 8,
                }
            ),
            Command.create(
                {
                    "name": self.env._("Optional Products Section"),
                    "display_type": "line_section",
                    "is_optional": True,
                    "product_qty": 0,
                }
            ),
            Command.create(
                {
                    "product_id": self.env.ref("product.product_product_16").id,
                    "product_qty": 0,
                }
            ),
            Command.create(
                {
                    "product_id": self.env.ref("product.product_product_7").id,
                    "product_qty": 0,
                }
            ),
            Command.create(
                {
                    "product_id": self.env.ref("product.product_product_12").id,
                    "product_qty": 0,
                }
            ),
        ]
