import math
from collections import defaultdict

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import format_amount

PERIOD_RATIO = {
    "hour": 1,
    "day": 24,
    "week": 24 * 7,
    "month": 24 * 31,
    "year": 24 * 31 * 12,
}

_debug = DebugLog(__name__)


class ProductPricing(models.Model):
    _name = "product.pricing"
    _description = "Pricing rule of rental products"
    _order = "product_template_id,price,pricelist_id,recurrence_id"

    name = fields.Char(related="recurrence_id.duration_display")
    description = fields.Char(compute="_compute_description")
    recurrence_id = fields.Many2one(
        comodel_name="sale.temporal.recurrence",
        string="Renting Period",
        required=True,
    )
    price = fields.Monetary(
        default=1.0,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_currency_id",
        store=True,
    )
    product_template_id = fields.Many2one(
        comodel_name="product.template",
        index="btree_not_null",
        ondelete="cascade",
        help="Select products on which this pricing will be applied.",
    )
    product_variant_ids = fields.Many2many(
        comodel_name="product.product",
        help="Select Variants of the Product for which this rule applies."
        "Leave empty if this rule applies for any variant of this template.",
    )
    pricelist_id = fields.Many2one(
        comodel_name="product.pricelist",
        index="btree_not_null",
        ondelete="cascade",
    )
    company_id = fields.Many2one(related="pricelist_id.company_id")

    @api.constrains("recurrence_id")
    def _check_unique_night_period(self) -> None:
        for pricing in self:
            all_pricings = pricing.product_template_id.product_pricing_ids
            overnight_count = sum(p.recurrence_id.overnight for p in all_pricings)
            if overnight_count and overnight_count != len(all_pricings):
                _debug.logic(
                    "pricing_rejected",
                    pricing=pricing,
                    reason="nightly_mixed_with_other",
                )
                raise ValidationError(
                    self.env._(
                        "Nightly periods cannot be mixed with other rental periods."
                    )
                )

    @api.constrains(
        "product_template_id", "pricelist_id", "recurrence_id", "product_variant_ids"
    )
    def _check_unique_parameters(self) -> None:
        conflict_counter = defaultdict(int)
        for price in self.product_template_id.product_pricing_ids:
            key_list = [
                price.product_template_id.id,
                price.pricelist_id,
                price.recurrence_id,
            ]
            variants = price.product_variant_ids.ids or [self.env._("all variants")]
            pricing_has_all_variants = (
                price.product_template_id.product_variant_count
                == len(price.product_variant_ids)
            )
            variants = (
                [self.env._("all variants")] if pricing_has_all_variants else variants
            )
            for v in variants:
                key_list.append(v)
                key_val = tuple(key_list)
                conflict_counter[key_val] += 1
        pricing_issues = [k for k, v in conflict_counter.items() if v > 1]
        if pricing_issues:
            _debug.logic(
                "pricing_rejected",
                pricings=self,
                reason="duplicate_rule",
                conflicts=len(pricing_issues),
            )
            raise ValidationError(
                self.env._(
                    "You cannot have multiple pricing for the same variant, recurrence and pricelist"
                )
            )

    def _compute_description(self) -> None:
        for pricing in self:
            pricing.description = self.env._(
                "%(amount)s / %(duration)s",
                amount=format_amount(
                    self.env, amount=pricing.price, currency=pricing.currency_id
                ),
                duration=pricing.recurrence_id.duration_display,
            )

    @api.depends("pricelist_id", "pricelist_id.currency_id")
    def _compute_currency_id(self) -> None:
        for pricing in self:
            pricing.currency_id = (
                pricing.pricelist_id.currency_id or self.env.company.currency_id
            )

    def _get_price_for_duration(self, duration, unit):
        self.check_singleton()
        if duration <= 0 or self.recurrence_id.duration <= 0:
            return self.price
        if unit != self.recurrence_id.unit:
            converted_duration = math.ceil(
                (duration * PERIOD_RATIO[unit])
                / (self.recurrence_id.duration * PERIOD_RATIO[self.recurrence_id.unit])
            )
        else:
            converted_duration = math.ceil(duration / self.recurrence_id.duration)
        return self.price * converted_duration

    @api.model
    def _get_duration_vals(self, start_date, end_date):
        duration = end_date - start_date
        vals = {"hour": (duration.days * 24 + duration.seconds / 3600)}
        vals["day"] = math.ceil(vals["hour"] / 24)
        vals["week"] = math.ceil(vals["day"] / 7)
        duration_diff = relativedelta(end_date, start_date)
        months = (
            1
            if duration_diff.days or duration_diff.hours or duration_diff.minutes
            else 0
        )
        months += duration_diff.months
        months += duration_diff.years * 12
        vals["month"] = months
        vals["year"] = months / 12
        return vals

    def _applies_to(self, product) -> bool:
        self.check_singleton()
        return self.product_template_id == product.product_tmpl_id and (
            not self.product_variant_ids or product in self.product_variant_ids
        )

    @api.model
    def _get_first_suitable_pricing(self, product, pricelist=None):
        return self._get_suitable_pricings(product, pricelist=pricelist, first=True)

    @api.model
    def _get_suitable_pricings(self, product, pricelist=None, first=False):
        is_product_template = product._name == "product.template"
        available_pricings = self.env["product.pricing"]
        if pricelist:
            for pricing in product.product_pricing_ids:
                if pricing.pricelist_id == pricelist and (
                    is_product_template or pricing._applies_to(product)
                ):
                    if first:
                        return pricing
                    available_pricings |= pricing

        for pricing in product.product_pricing_ids:
            if not pricing.pricelist_id and (
                is_product_template or pricing._applies_to(product)
            ):
                if first:
                    return pricing
                available_pricings |= pricing

        return available_pricings
