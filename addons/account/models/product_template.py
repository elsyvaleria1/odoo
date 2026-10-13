from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


ACCOUNT_DOMAIN = "[('account_type', 'not in', ('asset_receivable','liability_payable','asset_cash','liability_credit_card','off_balance'))]"


class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ["product.template", "mixin.fiscal.country.codes"]

    property_account_income_id = fields.Many2one(
        comodel_name="account.account",
        string="Income Account",
        company_dependent=True,
        domain=ACCOUNT_DOMAIN,
        ondelete="restrict",
        help="Keep this field empty to use the default value from the product category.",
    )
    property_account_expense_id = fields.Many2one(
        comodel_name="account.account",
        string="Expense Account",
        company_dependent=True,
        domain=ACCOUNT_DOMAIN,
        ondelete="restrict",
        help="Keep this field empty to use the default value from the product category. If anglo-saxon accounting with automated valuation method is configured, the expense account on the product category will be used.",
    )
    account_tag_ids = fields.Many2many(
        comodel_name="account.account.tag",
        string="Account Tags",
        domain="[('applicability', '=', 'products')]",
        help="Tags to be set on the base and tax journal items created for this product.",
    )

    def _get_product_accounts(self, fiscal_pos=None):
        self.check_singleton()
        company = self.env.company
        accounts = {
            "income": (
                self.property_account_income_id
                or self._get_category_account("property_account_income_categ_id")
                or company.account_config_id.income_account_id
            ),
            "expense": (
                self.property_account_expense_id
                or self._get_category_account("property_account_expense_categ_id")
                or company.account_config_id.expense_account_id
            ),
        }
        return self._map_product_accounts(accounts, fiscal_pos)

    def _map_product_accounts(self, accounts, fiscal_pos):
        if not fiscal_pos:
            return accounts
        return {
            key: fiscal_pos.map_account(value)
            if value._name == "account.account"
            else value
            for key, value in accounts.items()
        }

    def _get_category_account(self, field_name):
        categ = self.categ_id
        while categ:
            account = categ[field_name]
            if account:
                return account
            categ = categ.parent_id
        return self.env["account.account"]

    @api.depends("company_id")
    def _compute_fiscal_country_codes(self):
        return super()._compute_fiscal_country_codes()

    def _get_fiscal_country_companies(self):
        return self.company_id or super()._get_fiscal_country_companies()

    @_debug.perf.timed
    def _check_uom_not_used_on_a_posted_entry(self) -> None:
        if not self:
            return
        self.env["account.move.line"].flush_model(["product_id", "parent_state"])
        self.env["product.product"].flush_model(["product_tmpl_id"])
        self.env.cr.execute(
            """
            SELECT prod_template.id
              FROM account_move_line line
              JOIN product_product prod_variant ON line.product_id = prod_variant.id
              JOIN product_template prod_template ON prod_variant.product_tmpl_id = prod_template.id
             WHERE prod_template.id = ANY(%s)
               AND line.parent_state = 'posted'
             LIMIT 1
        """,
            [list(self.ids)],
        )
        row = self.env.cr.fetchone()
        if row:
            _debug.logic("uom_change_rejected", templates=self, used_template=row[0])
            raise ValidationError(
                self.env._(
                    "%(product)s is already used on posted journal entries.\n"
                    "To change its Unit of Measure, archive it and create a new product.",
                    product=self.browse(row[0]).display_name,
                )
            )

    @api.model_create_multi
    @_debug.perf.timed
    def create(self, vals_list):
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "create",
                model=self._name,
                count=len(vals_list),
                fields=sorted({key for vals in vals_list for key in vals}),
            )
        return super().create(vals_list)

    @_debug.perf.timed
    def write(self, vals):
        _debug.lifecycle("write", records=self, fields=sorted(vals))
        if "uom_id" in vals:
            self.filtered(
                lambda product: product.uom_id.id != vals["uom_id"]
            )._check_uom_not_used_on_a_posted_entry()
        return super().write(vals)
