from typing import Self

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Command, Domain

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.const import REPORT_REASONS_MAPPING


class PaymentMethod(models.Model):
    _name = "payment.method"
    _description = "Provider Payment Method"
    _order = "active desc, sequence, name"

    name = fields.Char(
        translate=True,
        required=True,
    )
    code = fields.Char(
        required=True,
        help="The technical code of this payment method.",
    )
    sequence = fields.Integer(default=1)
    primary_payment_method_id = fields.Many2one(
        comodel_name="payment.method",
        index="btree_not_null",
        help="The primary payment method of the current payment method, if the latter is a brand."
        '\nFor example, "Card" is the primary payment method of the card brand "VISA".',
    )
    brand_ids = fields.One2many(
        comodel_name="payment.method",
        inverse_name="primary_payment_method_id",
        string="Brands",
        help="The brands of the payment methods that will be displayed on the payment form.",
    )
    is_primary = fields.Boolean(
        string="Is Primary Payment Method",
        compute="_compute_is_primary",
        search="_search_is_primary",
    )
    provider_ids = fields.Many2many(
        comodel_name="payment.provider",
        string="Providers",
        help="The list of providers supporting this payment method.",
    )
    active = fields.Boolean(default=True)
    image = fields.Image(
        max_width=64,
        max_height=64,
        required=True,
        help="The base image used for this payment method; in a 64x64 px format.",
    )
    image_payment_form = fields.Image(
        related="image",
        string="The resized image displayed on the payment form.",
        max_width=45,
        max_height=30,
        store=True,
    )

    support_tokenization = fields.Boolean(
        string="Tokenization",
        help="Tokenization is the process of saving the payment details as a token that can later"
        " be reused without having to enter the payment details again.",
    )
    support_express_checkout = fields.Boolean(
        string="Express Checkout",
        help="Express checkout allows customers to pay faster by using a payment method that"
        " provides all required billing and shipping information, thus allowing to skip the"
        " checkout process.",
    )
    support_manual_capture = fields.Selection(
        selection=[
            ("none", "Unsupported"),
            ("full_only", "Full Only"),
            ("partial", "Full & Partial"),
        ],
        string="Manual Capture",
        default="none",
        required=True,
        help="The payment is authorized and captured in two steps instead of one.",
    )
    support_refund = fields.Selection(
        selection=[
            ("none", "Unsupported"),
            ("full_only", "Full Only"),
            ("partial", "Full & Partial"),
        ],
        string="Refund",
        default="none",
        required=True,
        help="Refund is a feature allowing to refund customers directly from the payment in Odoo.",
    )
    supported_country_ids = fields.Many2many(
        comodel_name="res.country",
        string="Countries",
        help="The list of countries in which this payment method can be used (if the provider"
        " allows it). In other countries, this payment method is not available to customers.",
    )
    supported_currency_ids = fields.Many2many(
        comodel_name="res.currency",
        string="Currencies",
        context={"active_test": False},
        help="The list of currencies for that are supported by this payment method (if the provider"
        " allows it). When paying with another currency, this payment method is not available "
        "to customers.",
    )

    @api.depends("primary_payment_method_id")
    def _compute_is_primary(self) -> None:
        for payment_method in self:
            payment_method.is_primary = not payment_method.primary_payment_method_id

    def _search_is_primary(self, operator, value):
        if operator not in ("in", "not in"):
            return NotImplemented
        return [("primary_payment_method_id", operator, [False])]

    @api.onchange("active", "provider_ids", "support_tokenization")
    def _onchange_warn_before_disabling_tokens(self) -> dict | None:
        disabling = self._origin.active and not self.active
        detached_providers = self._origin.provider_ids.filtered(
            lambda p: p.id not in self.provider_ids.ids
        )
        blocking_tokenization = (
            self._origin.support_tokenization and not self.support_tokenization
        )
        if disabling or detached_providers or blocking_tokenization:
            related_tokens = (
                self.env["payment.token"]
                .with_context(active_test=True)
                .search(
                    Domain(
                        "payment_method_id",
                        "in",
                        (self._origin + self._origin.brand_ids).ids,
                    )
                    & (
                        Domain("provider_id", "in", detached_providers.ids)
                        if detached_providers
                        else Domain.TRUE
                    ),
                )
            )
            if related_tokens:
                return {
                    "warning": {
                        "title": self.env._("Warning"),
                        "message": self.env._(
                            "This action will also archive %s tokens that are registered with this "
                            "payment method.",
                            len(related_tokens),
                        ),
                    }
                }
        return None

    @api.onchange("provider_ids")
    def _onchange_provider_ids_warn_before_attaching_payment_method(
        self,
    ) -> dict | None:
        attached_providers = self.provider_ids.filtered(
            lambda p: p.id.origin not in self._origin.provider_ids.ids
        )
        if attached_providers:
            return {
                "warning": {
                    "title": self.env._("Warning"),
                    "message": self.env._(
                        "Please make sure that %(payment_method)s is supported by %(provider)s.",
                        payment_method=self.name,
                        provider=", ".join(attached_providers.mapped("name")),
                    ),
                }
            }
        return None

    @api.constrains("active", "support_manual_capture")
    def _check_manual_capture_supported_by_providers(self) -> None:
        incompatible_pms = self.filtered(
            lambda pm: (
                pm.active
                and (pm.primary_payment_method_id or pm).support_manual_capture
                == "none"
                and any(provider.capture_manually for provider in pm.provider_ids)
            ),
        )
        if incompatible_pms:
            raise ValidationError(
                self.env._(
                    "The following payment methods cannot be enabled because their payment provider has"
                    " manual capture activated: %s",
                    ", ".join(incompatible_pms.mapped("name")),
                )
            )

    def write(self, vals):
        archiving = vals.get("active") is False
        detached_provider_ids = (
            [v[0] for command, *v in vals["provider_ids"] if command == Command.UNLINK]
            if "provider_ids" in vals
            else []
        )
        blocking_tokenization = vals.get("support_tokenization") is False
        if archiving or detached_provider_ids or blocking_tokenization:
            linked_tokens = (
                self.env["payment.token"]
                .with_context(active_test=True)
                .search(
                    Domain("payment_method_id", "in", (self + self.brand_ids).ids)
                    & (
                        Domain("provider_id", "in", detached_provider_ids)
                        if detached_provider_ids
                        else Domain.TRUE
                    ),
                )
            )
            linked_tokens.active = False

        if vals.get("active"):
            for pm in self:
                primary_pm = pm if pm.is_primary else pm.primary_payment_method_id
                if not primary_pm.active and all(
                    p.state == "disabled" for p in primary_pm.provider_ids
                ):
                    raise UserError(
                        self.env._(
                            "This payment method needs a partner in crime; you should enable a payment"
                            " provider supporting this method first."
                        )
                    )

        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_if_not_default_payment_method(self) -> None:
        payment_method_unknown = self.env.ref("payment.payment_method_unknown")
        if payment_method_unknown in self:
            raise UserError(self.env._("You cannot delete the default payment method."))

    @api.ondelete(at_uninstall=False)
    def _unlink_if_not_linked_to_providers(self) -> None:
        if any(pm.provider_ids for pm in self):
            raise UserError(
                self.env._("You cannot delete a payment method linked to a provider.")
            )

    def _get_compatible_payment_methods(
        self,
        provider_ids,
        partner_id,
        currency_id=None,
        force_tokenization=False,
        is_express_checkout=False,
        report=None,
        **kwargs,
    ):
        payment_methods = self.env["payment.method"].search([("is_primary", "=", True)])
        payment_utils.add_to_report(report, payment_methods)

        unfiltered_pms = payment_methods
        payment_methods = payment_methods.filtered(
            lambda pm: any(p in provider_ids for p in pm.provider_ids.ids)
        )
        payment_utils.add_to_report(
            report,
            unfiltered_pms - payment_methods,
            available=False,
            reason=REPORT_REASONS_MAPPING["provider_not_available"],
        )

        partner = self.env["res.partner"].browse(partner_id)
        if partner.country_id:
            unfiltered_pms = payment_methods
            payment_methods = payment_methods.filtered(
                lambda pm: (
                    not pm.supported_country_ids
                    or partner.country_id.id in pm.supported_country_ids.ids
                )
            )
            payment_utils.add_to_report(
                report,
                unfiltered_pms - payment_methods,
                available=False,
                reason=REPORT_REASONS_MAPPING["incompatible_country"],
            )

        if currency_id:
            unfiltered_pms = payment_methods
            payment_methods = payment_methods.filtered(
                lambda pm: (
                    not pm.supported_currency_ids
                    or currency_id in pm.supported_currency_ids.ids
                )
            )
            payment_utils.add_to_report(
                report,
                unfiltered_pms - payment_methods,
                available=False,
                reason=REPORT_REASONS_MAPPING["incompatible_currency"],
            )

        if force_tokenization:
            unfiltered_pms = payment_methods
            payment_methods = payment_methods.filtered("support_tokenization")
            payment_utils.add_to_report(
                report,
                unfiltered_pms - payment_methods,
                available=False,
                reason=REPORT_REASONS_MAPPING["tokenization_not_supported"],
            )

        if is_express_checkout:
            unfiltered_pms = payment_methods
            payment_methods = payment_methods.filtered("support_express_checkout")
            payment_utils.add_to_report(
                report,
                unfiltered_pms - payment_methods,
                available=False,
                reason=REPORT_REASONS_MAPPING["express_checkout_not_supported"],
            )

        return payment_methods

    def _get_from_code(self, code, mapping=None) -> Self:
        generic_to_specific_mapping = mapping or {}
        specific_to_generic_mapping = {
            v: k for k, v in generic_to_specific_mapping.items()
        }
        return self.search(
            [("code", "=", specific_to_generic_mapping.get(code, code))], limit=1
        )
