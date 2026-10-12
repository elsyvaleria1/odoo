from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

if TYPE_CHECKING:
    from odoo.addons.sale.models.sale_order import SaleOrder

_debug = DebugLog(__name__)


class ApprovalCategory(models.Model):
    _inherit = "approval.category"

    approval_type = fields.Selection(
        selection_add=[("sale", "Sale")],
        ondelete={"sale": "cascade"},
    )
    target_model = fields.Selection(
        selection_add=[("sale.order", "Sale Order")],
        ondelete={"sale.order": "cascade"},
    )
    so_approval_mode = fields.Selection(
        selection=[
            ("amount", "Based on Amount"),
            ("partner", "Based on Customer"),
            ("product", "Based on Product Category"),
            ("credit", "Based on Credit Limit"),
            ("combined", "Combined Rules"),
        ],
        string="Sales Approval Trigger",
        default="combined",
        help="What triggers this approval category to be used",
    )
    check_credit_limit = fields.Boolean(
        string="Check Customer Credit Limit",
        help="If checked, this category only applies when creating this SO "
        "would cause the customer's receivable balance to exceed their credit "
        "limit. Use this to control customer credit exposure.\n\n"
        "Superseded once `account_credit` is installed: it clears this flag "
        "on every category in its pre_init_hook and hides this field on the "
        "form, so credit-driven approval is owned by its credit policy from "
        "then on. The flag stays writable through the ORM and the trigger still "
        "works if you set it, but nothing in the interface will.",
    )

    def _get_approval_mode_field(self) -> str:
        if self.approval_type == "sale":
            return "so_approval_mode"
        return super()._get_approval_mode_field()

    def _get_approval_mode_criteria(self) -> dict[str, tuple[str, ...]]:
        if self.approval_type != "sale":
            return super()._get_approval_mode_criteria()
        return {
            "amount": ("order_amount_min", "order_amount_max"),
            "partner": ("order_partner_ids",),
            "credit": ("order_partner_ids", "check_credit_limit"),
            "product": ("product_categ_ids", "product_ids"),
        }

    def _get_approval_mode_hidden_criteria(self) -> tuple[str, ...]:
        self.check_singleton()
        if self.approval_type == "sale" and not self.so_approval_mode:
            return ()
        return super()._get_approval_mode_hidden_criteria()

    @api.onchange("so_approval_mode")
    def _onchange_so_approval_mode(self) -> None:
        self._clear_approval_mode_hidden_criteria()

    def _check_customer_credit_exceeded(self, sale_order: SaleOrder) -> bool:
        self.check_singleton()
        partner = sale_order.partner_id.commercial_partner_id.sudo().with_company(
            sale_order.company_id,
        )
        if partner.credit_limit <= 0:
            _debug.logic(
                "credit_policy", order=sale_order, partner=partner, by="no_credit_limit"
            )
            return False

        so_amount_company = sale_order.currency_id._convert(
            sale_order.amount_total,
            sale_order.company_id.currency_id,
            sale_order.company_id,
            sale_order.date_order or fields.Date.today(),
        )
        _debug.logic(
            "credit_policy",
            order=sale_order,
            partner=partner,
            credit=partner.credit,
            order_amount=so_amount_company,
            limit=partner.credit_limit,
        )
        return partner.credit + so_amount_company > partner.credit_limit

    def _is_applicable_for(self, document: models.BaseModel) -> bool:
        self.check_singleton()
        if document._name != "sale.order":
            return super()._is_applicable_for(document)
        return (
            self.approval_type == "sale"
            and not self.target_model
            and self._is_matching_document(document)
        )

    def _is_matching_credit_policy(self, document: models.BaseModel) -> bool:
        if document._name != "sale.order":
            return super()._is_matching_credit_policy(document)
        if not self.check_credit_limit:
            _debug.logic(
                "credit_policy", category=self, order=document, by="check_disabled"
            )
            return True
        return self._check_customer_credit_exceeded(document)
