from collections.abc import Hashable
from typing import TYPE_CHECKING, Any

from odoo import api, fields, models
from odoo.exceptions import UserError

if TYPE_CHECKING:
    from odoo.addons.approval.models.approval_approver import ApprovalApprover
    from odoo.addons.approval.models.approval_category_step import (
        ApprovalCategoryStep,
    )
    from odoo.addons.approval_product.models.approval_request_line import (
        ApprovalRequestLine,
    )
    from odoo.addons.product.models.product_supplierinfo import ProductSupplierinfo


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    purchase_order_ids = fields.One2many(
        comodel_name="purchase.order",
        inverse_name="approval_request_id",
        readonly=True,
        help="Purchase orders that requested this approval themselves, as opposed "
        "to the ones this request created from its lines.",
    )
    count_purchase_order = fields.Integer(compute="_compute_count_purchase_order")

    @api.depends(
        "line_ids.purchase_order_line_id",
        "purchase_order_ids",
    )
    def _compute_count_purchase_order(self) -> None:
        origins = self._origin.filtered("id")
        orders_by_request = {}
        if origins:
            groups = (
                self.env["purchase.order"]
                .sudo()
                ._read_group(
                    [("approval_request_id", "in", origins.ids)],
                    groupby=["approval_request_id"],
                    aggregates=["id:array_agg"],
                )
            )
            orders_by_request = {
                request.id: set(order_ids) for request, order_ids in groups
            }

        for request in self:
            from_lines = set(
                request.sudo().line_ids.purchase_order_line_id.order_id.ids,
            )
            request.count_purchase_order = len(
                from_lines | orders_by_request.get(request._origin.id, set()),
            )

    def action_approve(
        self,
        approver: ApprovalApprover | None = None,
        steps: ApprovalCategoryStep | None = None,
    ) -> dict[str, Any] | None:
        result = super().action_approve(approver, steps)
        self._check_purchase_type_has_product_lines()
        return result

    def _is_purchase_target(self) -> bool:
        return self.target_model == "purchase.order"

    def _get_target_line_field(self) -> str:
        if self._is_purchase_target():
            return "purchase_order_line_id"
        return super()._get_target_line_field()

    def _get_target_line_parent_field(self) -> str:
        if self._is_purchase_target():
            return "order_id"
        return super()._get_target_line_parent_field()

    def _get_target_document_name(self) -> str:
        if self._is_purchase_target():
            return self.env._("Purchase Orders")
        return super()._get_target_document_name()

    def _get_target_document_label(self) -> str:
        if self._is_purchase_target():
            return self.env._("purchase order")
        return super()._get_target_document_label()

    def _get_target_log_label(self) -> str:
        if self._is_purchase_target():
            return self.env._("RFQs")
        return super()._get_target_log_label()

    def _get_target_log_prefix(self) -> str:
        if self._is_purchase_target():
            return self.env._("RFQ ")
        return super()._get_target_log_prefix()

    def _is_target_rollback_enabled(self) -> bool:
        if self._is_purchase_target():
            return True
        return super()._is_target_rollback_enabled()

    def _check_target_prerequisites(self, lines: ApprovalRequestLine) -> None:
        super()._check_target_prerequisites(lines)
        if self._is_purchase_target():
            lines._check_products_vendor()

    def _get_purchase_seller(self, line: ApprovalRequestLine) -> ProductSupplierinfo:
        return line.seller_id or line.product_id.with_company(
            line.company_id,
        )._select_seller(
            quantity=line.product_uom_qty,
            uom_id=line.product_id.uom_id,
        )

    def _get_target_group_key(self, line: ApprovalRequestLine) -> Hashable:
        if not self._is_purchase_target():
            return super()._get_target_group_key(line)
        return self._get_purchase_seller(line).partner_id.id

    def _prepare_target_document_values(
        self, key: Any, lines: ApprovalRequestLine
    ) -> dict[str, Any]:
        if not self._is_purchase_target():
            return super()._prepare_target_document_values(key, lines)
        if not key:
            raise UserError(
                self.env._(
                    "No vendor could be resolved for the product(s): %s.\n\n"
                    "Select a vendor on the approval line, or configure one on "
                    "the product whose minimum quantity the line satisfies.",
                    ", ".join(lines.mapped("product_id.display_name")),
                ),
            )
        seller = self._get_purchase_seller(lines[0])
        vendor = self.env["res.partner"].browse(key).with_company(self.company_id)
        return {
            "origin": self.name,
            "partner_id": vendor.id,
            "company_id": self.company_id.id,
            "payment_term_id": vendor.property_supplier_payment_term_id.id,
            "fiscal_position_id": self.env["account.fiscal.position"]
            .with_company(self.company_id)
            ._get_fiscal_position(vendor)
            .id,
            "currency_id": seller.currency_id.id,
        }

    def _prepare_target_line_values(
        self,
        line: ApprovalRequestLine,
        key: Any,
        document: models.BaseModel,
        lines: ApprovalRequestLine,
    ) -> dict[str, Any]:
        if not self._is_purchase_target():
            return super()._prepare_target_line_values(line, key, document, lines)
        seller = self._get_purchase_seller(line)
        vendor = self.env["res.partner"].browse(key)
        seller_uom_qty = line.product_uom_id._get_quantity_in_unit(
            line.quantity,
            seller.product_uom_id,
        )
        return self.env["purchase.order.line"]._prepare_purchase_order_line(
            line.product_id,
            seller_uom_qty,
            seller.product_uom_id,
            line.company_id,
            vendor,
            document,
            seller,
        )

    def action_create_purchase_orders(self) -> dict[str, Any]:
        return self.action_create_target_documents()

    def action_view_purchase_order(self) -> dict[str, Any]:
        if self._is_purchase_target():
            return self.action_view_target_documents()
        self.check_singleton()
        return {
            "name": self.env._("Purchase Orders"),
            "type": "ir.actions.act_window",
            "res_model": "purchase.order",
            "view_mode": "list,form",
            "domain": [("id", "in", self._get_all_purchase_orders().ids)],
        }

    def _get_all_purchase_orders(self) -> models.BaseModel:
        return self._get_documents_of_model(
            "purchase.order",
            "purchase_order_line_id",
            "order_id",
        )

    def _check_withdraw_allowed(self) -> None:
        super()._check_withdraw_allowed()
        self._check_withdraw_blocked_by(
            self._get_all_purchase_orders(),
            self.env._("purchase order"),
        )

    def _check_confirm(self) -> None:
        super()._check_confirm()
        self._check_purchase_type_has_product_lines()

    def _check_purchase_type_has_product_lines(self) -> None:
        if self.target_model == "purchase.order":
            if not self.line_ids:
                raise UserError(
                    self.env._(
                        "This is an empty purchase request. Please add product lines.",
                    ),
                )
            if self.has_product == "no":
                raise UserError(
                    self.env._(
                        "This approval category is configured to create purchase "
                        "orders but does not have product lines enabled. "
                        "Please contact your administrator.",
                    ),
                )
