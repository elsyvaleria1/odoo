from odoo import api, fields, models

from odoo.addons.account_intrastat.models.account_intrastat_code import (
    SUPPLEMENTARY_UNITS,
)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    intrastat_code_id = fields.Many2one(
        comodel_name="account.intrastat.code",
        string="Commodity Code",
        compute="_compute_intrastat_values",
        inverse="_inverse_intrastat_code_id",
        readonly=False,
    )
    intrastat_supplementary_unit = fields.Selection(
        selection=SUPPLEMENTARY_UNITS,
        compute="_compute_intrastat_values",
    )
    intrastat_supplementary_unit_amount = fields.Float(
        compute="_compute_intrastat_values",
        inverse="_inverse_intrastat_supplementary_unit_amount",
        readonly=False,
        help="The number of supplementary units per product quantity.",
    )
    intrastat_origin_country_id = fields.Many2one(
        comodel_name="res.country",
        string="Country of Origin",
        compute="_compute_intrastat_values",
        inverse="_inverse_intrastat_origin_country_id",
        readonly=False,
    )
    valid_intrastat_code_ids = fields.Many2many(
        comodel_name="account.intrastat.code",
        string="Intrastat Code IDs",
        compute="_compute_valid_intrastat_code_ids",
    )
    intrastat_code_domain = fields.Char(compute="_compute_intrastat_code_domain")
    account_fiscal_country_group_codes = fields.Json(
        related="company_id.account_config_id.account_fiscal_country_group_codes"
    )

    @api.depends("type")
    def _compute_intrastat_code_domain(self) -> None:
        country_id = self.env.company.tax_config_id.account_fiscal_country_id.id
        service_codes_available = self.env["account.intrastat.code"].search_count(
            [
                ("country_id", "in", (country_id, False)),
                ("type", "=", "service"),
            ],
            limit=1,
        )
        for product in self:
            code_type = (
                "service"
                if service_codes_available and product.type == "service"
                else "commodity"
            )
            product.intrastat_code_domain = str(
                [
                    ("country_id", "in", (country_id, False)),
                    ("type", "=", code_type),
                ]
            )

    @api.depends("product_variant_ids")
    def _compute_intrastat_values(self) -> None:
        for product_template in self:
            variant = product_template.product_variant_ids[:1]
            product_template.intrastat_code_id = variant.intrastat_code_id
            product_template.intrastat_supplementary_unit = (
                variant.intrastat_code_id.supplementary_unit
            )
            product_template.intrastat_supplementary_unit_amount = (
                variant.intrastat_supplementary_unit_amount
            )
            product_template.intrastat_origin_country_id = (
                variant.intrastat_origin_country_id
            )

    @api.depends("type")
    def _compute_valid_intrastat_code_ids(self) -> None:
        valid_intrastat_code = dict(
            self.env["account.intrastat.code"]._read_group(
                domain=[
                    (
                        "country_id",
                        "in",
                        (
                            self.env.company.tax_config_id.account_fiscal_country_id.id,
                            False,
                        ),
                    )
                ],
                groupby=["type"],
                aggregates=["id:recordset"],
            )
        )
        for product in self:
            if "service" in valid_intrastat_code and product.type == "service":
                valid_codes = valid_intrastat_code["service"]
            else:
                valid_codes = valid_intrastat_code["commodity"]
            product.valid_intrastat_code_ids = valid_codes

    def _inverse_intrastat_code_id(self) -> None:
        for product_template in self:
            product_template.product_variant_ids.intrastat_code_id = (
                product_template.intrastat_code_id
            )

    def _inverse_intrastat_supplementary_unit_amount(self) -> None:
        for product_template in self:
            product_template.product_variant_ids.intrastat_supplementary_unit_amount = (
                product_template.intrastat_supplementary_unit_amount
            )

    def _inverse_intrastat_origin_country_id(self) -> None:
        for product_template in self:
            product_template.product_variant_ids.intrastat_origin_country_id = (
                product_template.intrastat_origin_country_id
            )

    def _get_related_fields_variant_template(self):
        fields = super()._get_related_fields_variant_template()
        fields += [
            "intrastat_code_id",
            "intrastat_origin_country_id",
            "intrastat_supplementary_unit",
            "intrastat_supplementary_unit_amount",
        ]
        return fields


class ProductProduct(models.Model):
    _inherit = "product.product"

    intrastat_code_id = fields.Many2one(comodel_name="account.intrastat.code")
    intrastat_supplementary_unit = fields.Selection(
        related="intrastat_code_id.supplementary_unit"
    )
    intrastat_supplementary_unit_amount = fields.Float(
        string="Supplementary Units",
        help="The number of supplementary units per product quantity.",
    )
    intrastat_origin_country_id = fields.Many2one(
        comodel_name="res.country",
        string="Country of Origin",
    )

    @api.depends("intrastat_supplementary_unit")
    def _compute_intrastat_supplementary_unit_amount(self) -> None:
        for product in self:
            if not product.intrastat_supplementary_unit:
                product.intrastat_supplementary_unit_amount = 0

    def _get_import_product_classification_specs(self):
        return super()._get_import_product_classification_specs() + [
            {
                "value_key": "intrastat_code",
                "field": "intrastat_code_id",
                "comodel": "account.intrastat.code",
                "code_field": "code",
            },
        ]
