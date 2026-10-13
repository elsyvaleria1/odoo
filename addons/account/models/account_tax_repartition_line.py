from typing import Self

from odoo import api, fields, models
from odoo.libs.json import dumps as json_dumps
from odoo.tools import SQL


class AccountTaxRepartitionLine(models.Model):
    _inherit = "account.tax.repartition.line"

    account_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'off_balance'))]",
        check_company=True,
        help="Account on which to post the tax amount",
    )
    tag_ids = fields.Many2many(
        comodel_name="account.account.tag",
        string="Tax Grids",
        copy=True,
        domain=[("applicability", "=", "taxes")],
        ondelete="restrict",
    )
    use_in_tax_closing = fields.Boolean(
        string="Tax Closing Entry",
        compute="_compute_use_in_tax_closing",
        precompute=True,
        store=True,
        readonly=False,
    )
    tag_ids_domain = fields.Binary(
        string="tag domain",
        compute="_compute_tag_ids_domain",
        help="Dynamic domain used for the tag that can be set on tax",
    )

    def _sorted_for_positional_pairing(self) -> Self:
        return self.sorted(
            lambda line: (
                line.document_type,
                line.repartition_type,
                line.sequence,
                line.factor_percent,
                line.account_id.id or 0,
            )
        )

    @api.model
    def _remap_move_lines(self, mapping, company_ids=None) -> int:
        if not mapping:
            return 0
        AccountMoveLine = self.env["account.move.line"]
        AccountMoveLine.flush_model(["tax_repartition_line_id"])
        self.env.cr.execute(
            SQL(
                """
                UPDATE account_move_line
                   SET tax_repartition_line_id =
                       (%(mapping)s::jsonb->>tax_repartition_line_id::text)::int
                 WHERE tax_repartition_line_id = ANY(%(old_ids)s)
                   %(company_filter)s
                """,
                mapping=json_dumps({str(k): v for k, v in mapping.items()}),
                old_ids=list(mapping),
                company_filter=(
                    SQL("AND company_id = ANY(%s)", list(company_ids))
                    if company_ids is not None
                    else SQL()
                ),
            )
        )
        AccountMoveLine.invalidate_model(["tax_repartition_line_id"])
        return self.env.cr.rowcount

    @api.depends_context("company")
    def _compute_tag_ids_domain(self) -> None:
        for rep_line in self:
            company = rep_line.tax_id._get_settings_company()
            allowed_country_ids = (
                False,
                company.tax_config_id.account_fiscal_country_id.id,
                *company.tax_config_id.multi_vat_foreign_country_ids.ids,
            )
            rep_line.tag_ids_domain = [
                ("applicability", "=", "taxes"),
                ("country_id", "in", allowed_country_ids),
            ]

    @api.depends("account_id", "repartition_type")
    def _compute_use_in_tax_closing(self) -> None:
        for rep_line in self:
            rep_line.use_in_tax_closing = (
                rep_line.repartition_type == "tax"
                and rep_line.account_id
                and rep_line.account_id.internal_group not in ("income", "expense")
            )

    @api.onchange("repartition_type")
    def _onchange_repartition_type(self) -> None:
        if self.repartition_type == "base":
            self.account_id = None

    def _get_aml_target_tax_account(self, force_caba_exigibility=False):
        self.check_singleton()
        if (
            not force_caba_exigibility
            and self.tax_id.tax_exigibility == "on_payment"
            and not self.env.context.get("caba_no_transition_account")
        ):
            return self.tax_id.cash_basis_transition_account_id
        else:
            return self.account_id
