from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

from odoo.addons.account.tools.account_prefix import (
    get_account_prefix_placeholder,
    split_account_prefixes,
)

_debug = DebugLog(__name__)


class AccountAnalyticApplicability(models.Model):
    _inherit = "account.analytic.applicability"
    _description = "Analytic Plan's Applicabilities"

    business_domain = fields.Selection(
        selection_add=[
            ("invoice", "Invoice"),
            ("bill", "Vendor Bill"),
        ],
        ondelete={
            "invoice": "cascade",
            "bill": "cascade",
        },
    )
    account_prefix = fields.Char(
        string="Financial Accounts Prefixes",
        help="Prefix that defines which accounts from the financial accounting this applicability should apply on.",
    )
    product_categ_id = fields.Many2one(
        comodel_name="product.category",
        string="Product Category",
    )
    display_account_prefix = fields.Boolean(
        compute="_compute_display_account_prefix",
        help="Defines if the field account prefix should be displayed",
    )
    account_prefix_placeholder = fields.Char(
        compute="_compute_account_prefix_placeholder"
    )

    @api.depends("account_prefix", "business_domain")
    @_debug.perf.timed
    def _compute_account_prefix_placeholder(self) -> None:
        placeholders = {}
        for applicability in self:
            if applicability.business_domain == "bill":
                key = ("expense", "60, 61, 62")
            else:
                key = ("income", "40, 41, 42")
            if key not in placeholders:
                placeholders[key] = get_account_prefix_placeholder(self.env, *key)
            _debug.logic(
                "placeholder_prefixes_chosen",
                domain=applicability.business_domain,
                account_type=key[0],
                placeholder=placeholders[key],
            )
            applicability.account_prefix_placeholder = placeholders[key]

    def _get_score(self, **kwargs):
        score = super()._get_score(**kwargs)
        if score == -1:
            return -1
        product = self.env["product.product"].browse(kwargs.get("product"))
        account = self.env["account.account"].browse(kwargs.get("account"))
        if account_prefixes := split_account_prefixes(self.account_prefix):
            if account.code and account.code.startswith(account_prefixes):
                score += 1
            else:
                _debug.logic(
                    "applicability_rejected",
                    applicability=self,
                    reason="account_prefix",
                    account=account,
                )
                return -1
        if self.product_categ_id:
            if product and product.categ_id == self.product_categ_id:
                score += 1
            else:
                _debug.logic(
                    "applicability_rejected",
                    applicability=self,
                    reason="product_category",
                    product=product,
                )
                return -1
        return score

    @api.depends("business_domain")
    def _compute_display_account_prefix(self) -> None:
        for applicability in self:
            applicability.display_account_prefix = applicability.business_domain in (
                "general",
                "invoice",
                "bill",
            )
