from odoo import api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError, ValidationError
from odoo.tools import frozendict


class PaymentToken(models.Model):
    _name = "payment.token"
    _order = "partner_id, id desc"
    _description = "Payment Token"
    _check_company_auto = True
    _rec_names_search = ["payment_details", "partner_id", "provider_id"]
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False, hierarchy="parent_of"),
            "partner": "partner_id",
        }
    )

    provider_id = fields.Many2one(
        comodel_name="payment.provider",
        required=True,
    )
    provider_code = fields.Selection(
        related="provider_id.code",
        string="Provider Code",
    )
    company_id = fields.Many2one(
        related="provider_id.company_id",
    )
    payment_method_id = fields.Many2one(
        comodel_name="payment.method",
        readonly=True,
        required=True,
    )
    payment_method_code = fields.Char(
        related="payment_method_id.code",
        string="Payment Method Code",
    )
    payment_details = fields.Char(
        help="The clear part of the payment method's payment details."
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        index=True,
        required=True,
    )
    provider_ref = fields.Char(
        string="Provider Reference",
        required=True,
        help="The provider reference of the token of the transaction.",
    )
    transaction_ids = fields.One2many(
        comodel_name="payment.transaction",
        inverse_name="token_id",
        string="Payment Transactions",
    )
    active = fields.Boolean(default=True)

    @api.depends("payment_details", "create_date")
    def _compute_display_name(self):
        for token in self:
            token.display_name = token._prepare_display_name()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if "provider_id" in values:
                provider = self.env["payment.provider"].browse(values["provider_id"])

                values.update(self._prepare_provider_create_vals(provider.code, values))

        return super().create(vals_list)

    @api.model
    def _prepare_provider_create_vals(
        self, provider_code: str, values: ValuesType
    ) -> ValuesType:
        return {}

    def write(self, vals):
        if "active" in vals:
            if vals["active"]:
                if any(
                    not token.payment_method_id.active
                    or token.provider_id.state == "disabled"
                    for token in self
                ):
                    raise UserError(
                        self.env._(
                            "You can't unarchive tokens linked to inactive payment methods or disabled"
                            " providers."
                        )
                    )
            else:
                self.filtered("active").sudo()._handle_archiving()

        return super().write(vals)

    @api.constrains("partner_id")
    def _check_partner_is_never_public(self) -> None:
        for token in self:
            if token.partner_id.is_public:
                raise ValidationError(
                    self.env._("No token can be assigned to the public partner.")
                )

    def _handle_archiving(self) -> None:
        return

    def _get_available_tokens(
        self, providers_ids, partner_id, is_validation=False, **kwargs
    ):
        if not is_validation:
            return self.env["payment.token"].search(
                [("provider_id", "in", providers_ids), ("partner_id", "=", partner_id)]
            )
        else:
            partner = self.env["res.partner"].browse(partner_id)
            return self.env["payment.token"].search(
                [("partner_id", "in", [partner.id, partner.commercial_partner_id.id])]
            )

    def _prepare_display_name(self, *args, max_length=34, should_pad=True, **kwargs):
        self.check_singleton()

        if not self.create_date:
            return ""

        padding_length = max_length - len(self.payment_details or "")
        if not self.payment_details:
            create_date_str = self.create_date.strftime("%Y/%m/%d")
            display_name = self.env._(
                "Payment details saved on %(date)s", date=create_date_str
            )
        elif padding_length >= 2:
            padding = "•" * min(padding_length - 1, 4) + " " if should_pad else ""
            display_name = f"{padding}{self.payment_details}"
        elif padding_length > 0:
            display_name = self.payment_details
        else:
            display_name = self.payment_details[-max_length:] if max_length > 0 else ""
        return display_name

    def get_linked_records_info(self):
        self.check_singleton()
        return []
