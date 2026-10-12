from odoo import Command, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.approval.models.approval_category import CATEGORY_SELECTION


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    has_product = fields.Selection(
        selection=CATEGORY_SELECTION,
        default="no",
        required=True,
        tracking=True,
        help="Additional products that should be specified on the request.",
    )
    product_ids = fields.Many2many(
        comodel_name="product.product",
        relation="approval_category_product_rel",
        column1="category_id",
        column2="product_id",
        string="Allowed Products",
        help="Products admissible in the request lines of this category. "
        "In purchase/sale categories this same list also constrains category "
        "matching against the order, whatever the trigger is set to. "
        "Leave empty to allow all products.",
    )
    order_amount_currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_order_amount_currency_id",
        help="Currency the order amount criteria are expressed in. A global "
        "category has no company of its own, so it falls back to the active "
        "company's currency instead of leaving the thresholds currency-less.",
    )
    order_amount_min = fields.Monetary(
        string="Minimum Amount",
        currency_field="order_amount_currency_id",
        help="Orders with amount >= this value will use this category",
    )
    order_amount_max = fields.Monetary(
        string="Maximum Amount",
        currency_field="order_amount_currency_id",
        help="Orders with amount <= this value will use this category (0 = no limit)",
    )
    order_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="approval_category_partner_rel",
        column1="category_id",
        column2="partner_id",
        string="Specific Partners",
        help="If set, this category applies only to these partners",
    )
    product_categ_ids = fields.Many2many(
        comodel_name="product.category",
        relation="approval_category_product_categ_rel",
        column1="category_id",
        column2="product_categ_id",
        string="Product Categories",
        help="If set, this category applies when the order contains products "
        "from these categories",
    )

    @api.depends("company_id")
    @api.depends_context("company")
    def _compute_order_amount_currency_id(self) -> None:
        for category in self:
            category.order_amount_currency_id = (
                category.company_id.currency_id or self.env.company.currency_id
            )

    @api.constrains("order_amount_min", "order_amount_max")
    def _check_order_amount_range(self) -> None:
        for category in self:
            if category.order_amount_max <= 0:
                continue
            if category.order_amount_min > category.order_amount_max:
                raise ValidationError(
                    self.env._(
                        "Minimum amount (%(minimum)s) cannot be greater than "
                        "maximum amount (%(maximum)s) on category '%(name)s'.",
                        minimum=category.order_amount_min,
                        maximum=category.order_amount_max,
                        name=category.name,
                    ),
                )

    def _is_matching_document(self, document: models.BaseModel) -> bool:
        self.check_singleton()
        return (
            self._is_matching_amount(document)
            and self._is_matching_partner(document)
            and self._is_matching_product_category(document)
            and self._is_matching_product(document)
            and self._is_matching_credit_policy(document)
        )

    def _is_matching_amount(self, document: models.BaseModel) -> bool:
        minimum, maximum = self._get_order_amount_range_for(document)
        if minimum and document.amount_total < minimum:
            return False
        return not (maximum > 0 and document.amount_total > maximum)

    def _get_order_amount_range_for(
        self, document: models.BaseModel
    ) -> tuple[float, float]:
        self.check_singleton()
        threshold_currency = self.order_amount_currency_id
        document_currency = document.currency_id
        if not (threshold_currency and document_currency) or (
            threshold_currency == document_currency
        ):
            return self.order_amount_min, self.order_amount_max

        company = document.company_id or self.env.company
        date = fields.Date.context_today(self)
        if document.date_order:
            date = fields.Date.to_date(document.date_order)
        convert = threshold_currency._convert
        return (
            convert(self.order_amount_min, document_currency, company, date),
            convert(self.order_amount_max, document_currency, company, date),
        )

    def _is_matching_partner(self, document: models.BaseModel) -> bool:
        return not self.order_partner_ids or document.partner_id in (
            self.order_partner_ids
        )

    def _is_matching_product_category(self, document: models.BaseModel) -> bool:
        if not self.product_categ_ids:
            return True
        categories = document.line_ids.mapped("product_id.categ_id")
        return bool(
            categories.filtered_domain(
                [("id", "child_of", self.product_categ_ids.ids)],
            ),
        )

    def _is_matching_product(self, document: models.BaseModel) -> bool:
        if not self.product_ids:
            return True
        products = document.line_ids.mapped("product_id")
        return any(product in self.product_ids for product in products)

    def _is_matching_credit_policy(self, document: models.BaseModel) -> bool:
        return True

    def _get_approval_mode_field(self) -> str:
        return ""

    def _get_approval_mode_criteria(self) -> dict[str, tuple[str, ...]]:
        return {}

    def _get_approval_mode_hidden_criteria(self) -> tuple[str, ...]:
        self.check_singleton()
        mode_field = self._get_approval_mode_field()
        criteria = self._get_approval_mode_criteria()
        if not mode_field or not criteria:
            return ()

        mode = self[mode_field]
        if mode == "combined":
            return ()

        shown = set(criteria.get(mode, ()))
        governed = {name for names in criteria.values() for name in names}
        return tuple(sorted(governed - shown))

    def _clear_approval_mode_hidden_criteria(self) -> None:
        for category in self:
            for name in category._get_approval_mode_hidden_criteria():
                field = category._fields[name]
                if field.type in ("many2many", "one2many"):
                    category[name] = [Command.clear()]
                elif field.type in ("float", "monetary", "integer"):
                    category[name] = 0
                else:
                    category[name] = False
