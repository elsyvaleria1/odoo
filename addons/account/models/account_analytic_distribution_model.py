from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.account.tools.account_prefix import (
    get_account_prefix_placeholder,
    split_account_prefixes,
)

_debug = DebugLog(__name__)


class AccountAnalyticDistributionModel(models.Model):
    _inherit = "account.analytic.distribution.model"

    account_prefix = fields.Char(
        string="Accounts Prefix",
        help="This analytic distribution will apply to all financial accounts sharing the prefix specified.",
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        ondelete="cascade",
        check_company=True,
        help="Select a product for which the analytic distribution will be used (e.g. create new customer invoice or Sales order if we select this product, it will automatically take this as an analytic account)",
    )
    product_categ_id = fields.Many2one(
        comodel_name="product.category",
        string="Product Category",
        ondelete="cascade",
        help="Select a product category which will use analytic account specified in analytic default (e.g. create new customer invoice or Sales order if we select this product, it will automatically take this as an analytic account)",
    )
    prefix_placeholder = fields.Char(compute="_compute_prefix_placeholder")

    def _prepare_default_search_params(self):
        return super()._prepare_default_search_params() | {
            "product_id": False,
            "product_categ_id": False,
        }

    def _get_applicable_models(self, vals):
        applicable_models = super()._get_applicable_models(vals)
        account_code = vals.get("account_prefix") or ""

        def matches_account(model) -> bool:
            prefixes = split_account_prefixes(model.account_prefix)
            if not prefixes:
                return True
            matched = account_code.startswith(prefixes)
            if not matched:
                _debug.logic(
                    "distribution_model_rejected",
                    model=model,
                    reason="account_prefix",
                    prefixes=prefixes,
                )
            return matched

        return applicable_models.filtered(matches_account)

    @_debug.perf.timed
    def _create_domain(self, fname, value) -> list:
        if fname == "account_prefix":
            return []
        return super()._create_domain(fname, value)

    @api.depends("analytic_precision")
    @_debug.perf.timed
    def _compute_prefix_placeholder(self) -> None:
        self.prefix_placeholder = get_account_prefix_placeholder(
            self.env, "expense", "60, 61, 62"
        )
