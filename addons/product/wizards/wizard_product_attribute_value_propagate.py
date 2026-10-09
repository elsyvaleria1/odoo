from collections import defaultdict

from odoo import api, fields, models
from odoo.fields import Command
from odoo.tools import formatLang


class WizardProductAttributeValuePropagate(models.TransientModel):
    _name = "wizard.product.attribute.value.propagate"
    _description = "Update product attribute value"

    attribute_value_id = fields.Many2one(
        comodel_name="product.attribute.value",
        required=True,
    )
    mode = fields.Selection(
        selection=[
            ("add", "Add to existing products"),
            ("update_extra_price", "Update the extra price on existing products"),
        ],
        required=True,
    )
    message = fields.Char(compute="_compute_message")
    product_count = fields.Integer(compute="_compute_product_counts")
    changed_product_count = fields.Integer(compute="_compute_product_counts")

    @api.depends("product_count", "changed_product_count", "mode", "attribute_value_id")
    def _compute_message(self) -> None:
        self.message = ""
        for wizard in self:
            if wizard.mode == "add":
                wizard.message = self.env._(
                    'You are about to add the value "%(attribute_value)s" to %(product_count)s products.',
                    attribute_value=wizard.attribute_value_id.name,
                    product_count=wizard.product_count,
                )
            elif wizard.mode == "update_extra_price":
                wizard.message = self.env._(
                    'You are about to set the extra price of "%(attribute_value)s"'
                    " to %(price)s on %(product_count)s products. %(changed_count)s"
                    " of them currently use a different extra price, which will be"
                    " overwritten.",
                    attribute_value=wizard.attribute_value_id.name,
                    price=formatLang(
                        self.env,
                        wizard.attribute_value_id.default_extra_price,
                        dp="Product Price",
                    ),
                    product_count=wizard.product_count,
                    changed_count=wizard.changed_product_count,
                )

    def _get_domain_company(self) -> list:
        return [("product_tmpl_id.company_id", "in", self.env.companies.ids + [False])]

    def _get_domain_target_templates(self) -> list:
        return [("product_tmpl_id.active", "=", True), *self._get_domain_company()]

    def _get_domain_lines_to_extend(self) -> list:
        self.check_singleton()
        return [
            ("attribute_id", "=", self.attribute_value_id.attribute_id.id),
            ("value_ids", "not in", self.attribute_value_id.ids),
            *self._get_domain_target_templates(),
        ]

    def _get_domain_values_to_reprice(self) -> list:
        self.check_singleton()
        # Archived values and templates are repriced too, though not counted:
        # reactivating one keeps its stored price_extra.
        return [
            ("product_attribute_value_id", "=", self.attribute_value_id.id),
            *self._get_domain_company(),
        ]

    @api.depends("mode", "attribute_value_id")
    def _compute_product_counts(self) -> None:
        self.product_count = 0
        self.changed_product_count = 0
        adding = self.filtered(lambda wizard: wizard.mode == "add")
        repricing = self.filtered(lambda wizard: wizard.mode == "update_extra_price")
        if values := adding.attribute_value_id:
            Line = self.env["product.template.attribute.line"]
            lines_per_attribute = dict(
                Line._read_group(
                    [
                        ("attribute_id", "in", values.attribute_id.ids),
                        *self._get_domain_target_templates(),
                    ],
                    ["attribute_id"],
                    ["__count"],
                )
            )
            lines_per_value = dict(
                Line._read_group(
                    [
                        ("value_ids", "in", values.ids),
                        *self._get_domain_target_templates(),
                    ],
                    ["value_ids"],
                    ["__count"],
                )
            )
            for wizard in adding:
                value = wizard.attribute_value_id
                wizard.product_count = lines_per_attribute.get(
                    value.attribute_id, 0
                ) - lines_per_value.get(value, 0)
        if values := repricing.attribute_value_id:
            per_value = defaultdict(lambda: [0, 0])
            for value, price_extra, count in self.env[
                "product.template.attribute.value"
            ]._read_group(
                [
                    ("product_attribute_value_id", "in", values.ids),
                    ("ptav_active", "=", True),
                    *self._get_domain_target_templates(),
                ],
                ["product_attribute_value_id", "price_extra"],
                ["__count"],
            ):
                per_value[value][0] += count
                if price_extra != value.default_extra_price:
                    per_value[value][1] += count
            for wizard in repricing:
                wizard.product_count, wizard.changed_product_count = per_value[
                    wizard.attribute_value_id
                ]

    def action_confirm(self):
        self.check_singleton()
        if self.mode == "add":
            self.env["product.template.attribute.line"].search(
                self._get_domain_lines_to_extend()
            ).write({"value_ids": [Command.link(self.attribute_value_id.id)]})
        elif self.mode == "update_extra_price":
            self.env["product.template.attribute.value"].search(
                self._get_domain_values_to_reprice()
            ).write({"price_extra": self.attribute_value_id.default_extra_price})
