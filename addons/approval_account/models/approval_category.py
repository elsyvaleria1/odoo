from typing import Any

from odoo import api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.approval.models.approval_category import CATEGORY_SELECTION


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    approval_type = fields.Selection(
        selection_add=[
            ("accounting", "Accounting"),
            ("payment", "Payment"),
        ],
        ondelete={
            "accounting": "cascade",
            "payment": "cascade",
        },
    )
    target_model = fields.Selection(
        selection_add=[
            ("account.move", "Journal Entry"),
            ("account.payment", "Payment"),
        ],
        ondelete={"account.move": "cascade"},
    )
    account_move_type = fields.Selection(
        selection=[
            ("out_invoice", "Customer Invoice"),
            ("out_refund", "Customer Credit Note"),
            ("in_invoice", "Vendor Bill"),
            ("in_refund", "Vendor Credit Note"),
        ],
        default="in_invoice",
        help="Type of invoice/bill to create when this approval is granted. "
        "Only applicable when target_model is 'account.move'. "
        "General journal entries are not supported in creation flow.",
    )
    move_amount_currency_id = fields.Many2one(
        comodel_name="res.currency",
        compute="_compute_move_amount_currency_id",
        help="Currency the invoice/bill amount criteria are expressed in. "
        "A global category has no company of its own, so it falls back to "
        "the active company's currency instead of leaving the thresholds "
        "currency-less. That fallback is a display currency only: for a "
        "global category the criteria are read in the currency of the "
        "company the document belongs to.",
    )
    move_amount_min = fields.Monetary(
        currency_field="move_amount_currency_id",
        help="Invoices/bills with amount >= this value will use this category",
    )
    move_amount_max = fields.Monetary(
        currency_field="move_amount_currency_id",
        help="Invoices/bills with amount <= this value will use this category (0 = no limit)",
    )
    move_partner_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="approval_category_account_partner_rel",
        column1="category_id",
        column2="partner_id",
        help="If set, this category applies only to these partners",
    )
    journal_ids = fields.Many2many(
        comodel_name="account.journal",
        relation="approval_category_journal_rel",
        column1="category_id",
        column2="journal_id",
        help="If set, this category applies when move uses these journals",
    )
    move_auto_post = fields.Boolean(
        default=lambda self: self.env.company.auto_post_on_approval,
        help="Automatically post invoice/bill when all approvals are granted. "
        "Defaults from the company's Auto-Post on Approval setting; this field "
        "is what actually commands auto-posting per category.",
    )
    has_bsl = fields.Selection(
        selection=CATEGORY_SELECTION,
        string="Bank Statement Line",
        default="no",
        required=True,
        tracking=True,
        help="Specify if a bank statement line must be selected for this type of approval.",
    )
    has_journal = fields.Selection(
        selection=CATEGORY_SELECTION,
        default="no",
        required=True,
        tracking=True,
    )

    @api.depends("company_id")
    @api.depends_context("company")
    def _compute_move_amount_currency_id(self) -> None:
        for category in self:
            category.move_amount_currency_id = (
                category.company_id.currency_id or self.env.company.currency_id
            )

    @api.constrains("move_amount_min", "move_amount_max")
    def _check_move_amount_range(self) -> None:
        for category in self:
            if (
                category.move_amount_max > 0
                and category.move_amount_min > category.move_amount_max
            ):
                raise ValidationError(
                    self.env._(
                        "Minimum amount (%(minimum)s) cannot be greater than maximum amount (%(maximum)s).",
                        minimum=category.move_amount_min,
                        maximum=category.move_amount_max,
                    ),
                )

    @api.onchange("account_move_type")
    def _onchange_account_move_type(self) -> None:
        if self.account_move_type in (
            "in_invoice",
            "in_refund",
            "out_invoice",
            "out_refund",
        ):
            self.has_product = "required"
            self.has_quantity = "required"
            self.has_partner = "required"

    def _get_financial_verb(self) -> str:
        if self.approval_type == "payment" or self.target_model == "account.payment":
            return self.env._("a payment")
        if self.approval_type == "accounting" or self.target_model == "account.move":
            return self.env._("posting a journal entry")
        return super()._get_financial_verb()

    def _is_applicable_for(self, document: Any) -> bool:
        self.check_singleton()
        if document._name != "account.move":
            return super()._is_applicable_for(document)

        if self.approval_type != "accounting" or self.target_model:
            return False

        if not (
            self.move_amount_min
            or self.move_amount_max
            or self.move_partner_ids
            or self.journal_ids
        ):
            return False

        if self.move_amount_min or self.move_amount_max:
            amount = document._amount_total_company_currency()
            minimum, maximum = self._move_amount_range_in(document.company_id, document)
            if amount < minimum or 0 < maximum < amount:
                return False

        if self.move_partner_ids and document.partner_id not in self.move_partner_ids:
            return False

        return not (self.journal_ids and document.journal_id not in self.journal_ids)

    def _move_amount_range_in(self, company, document) -> tuple:
        self.check_singleton()
        company_currency = company.currency_id
        if not self.company_id:
            return self.move_amount_min, self.move_amount_max

        threshold_currency = self.move_amount_currency_id
        if not threshold_currency or threshold_currency == company_currency:
            return self.move_amount_min, self.move_amount_max

        date = document.date or fields.Date.context_today(document)
        convert = threshold_currency._convert
        return (
            convert(self.move_amount_min, company_currency, company, date),
            convert(self.move_amount_max, company_currency, company, date),
        )
