from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError

if TYPE_CHECKING:
    from odoo.addons.purchase.models.purchase_order import PurchaseOrder


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    approval_type = fields.Selection(
        selection_add=[("purchase", "Purchase")],
        ondelete={"purchase": "cascade"},
    )
    target_model = fields.Selection(
        selection_add=[("purchase.order", "Purchase Order")],
        ondelete={"purchase.order": "cascade"},
    )
    order_approval_mode = fields.Selection(
        selection=[
            ("amount", "Based on Amount"),
            ("partner", "Based on Vendor"),
            ("product", "Based on Product/Category"),
            ("debit", "Based on Vendor Debit"),
            ("combined", "Combined Rules"),
        ],
        string="Purchase Approval Trigger",
        default="combined",
        help="What triggers this approval category to be used",
    )
    check_debit_limit = fields.Boolean(
        string="Check Vendor Debit Limit",
        help="If checked, this category only applies when creating this PO "
        "would cause the vendor's payable balance to exceed the threshold. "
        "Use this to control vendor credit exposure.",
    )
    debit_limit_threshold = fields.Monetary(
        string="Vendor Debit Threshold",
        currency_field="company_currency_id",
        help="Maximum allowed payable balance for vendor, in the currency of "
        "the category's company — or, on a category shared by every company, "
        "in each order's own company currency. "
        "If vendor's total payable (including this PO) exceeds this threshold, "
        "this approval category applies.",
    )

    def _get_approval_mode_field(self) -> str:
        if self.approval_type == "purchase":
            return "order_approval_mode"
        return super()._get_approval_mode_field()

    def _get_approval_mode_criteria(self) -> dict[str, tuple[str, ...]]:
        if self.approval_type != "purchase":
            return super()._get_approval_mode_criteria()
        return {
            "amount": ("order_amount_min", "order_amount_max"),
            "partner": ("order_partner_ids",),
            "product": ("product_categ_ids",),
            "debit": ("check_debit_limit", "debit_limit_threshold"),
        }

    def _get_approval_mode_hidden_criteria(self) -> tuple[str, ...]:
        self.check_singleton()
        if self.approval_type == "purchase" and not self.order_approval_mode:
            return ()
        return super()._get_approval_mode_hidden_criteria()

    @api.onchange("order_approval_mode")
    def _onchange_order_approval_mode(self) -> None:
        self._clear_approval_mode_hidden_criteria()

    def _is_vendor_debit_exceeded(self, purchase_order: PurchaseOrder) -> bool:
        self.check_singleton()
        partner = purchase_order.partner_id.commercial_partner_id.sudo().with_company(
            purchase_order.company_id,
        )
        date = purchase_order.date_order or fields.Date.today()
        company_currency = purchase_order.company_id.currency_id
        po_amount_company = purchase_order.currency_id._convert(
            purchase_order.amount_total,
            company_currency,
            purchase_order.company_id,
            date,
        )
        threshold = self.debit_limit_threshold
        if self.company_currency_id and self.company_currency_id != company_currency:
            threshold = self.company_currency_id._convert(
                threshold,
                company_currency,
                purchase_order.company_id,
                date,
            )
        return partner.debit + po_amount_company > threshold

    def _is_applicable_for(self, document: models.BaseModel) -> bool:
        self.check_singleton()
        if document._name != "purchase.order":
            return super()._is_applicable_for(document)
        return (
            self.approval_type == "purchase"
            and not self.target_model
            and self._is_matching_document(document)
        )

    def _get_financial_verb(self) -> str:
        if self.approval_type == "purchase" or self.target_model == "purchase.order":
            return self.env._("confirming a purchase")
        return super()._get_financial_verb()

    def _is_matching_credit_policy(self, document: models.BaseModel) -> bool:
        if document._name != "purchase.order":
            return super()._is_matching_credit_policy(document)
        if not self.check_debit_limit:
            return True
        return self._is_vendor_debit_exceeded(document)

    @api.constrains("check_debit_limit", "debit_limit_threshold", "approval_type")
    def _check_debit_limit_threshold(self) -> None:
        for category in self:
            if category.approval_type != "purchase":
                continue
            if category.check_debit_limit and category.debit_limit_threshold <= 0:
                raise ValidationError(
                    self.env._(
                        "Set a vendor debit threshold above zero on '%(category)s', "
                        "or untick 'Check Vendor Debit Limit'. A zero threshold "
                        "used to leave the criterion switched on but inert.",
                        category=category.display_name,
                    ),
                )
