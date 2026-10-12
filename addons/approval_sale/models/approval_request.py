from typing import TYPE_CHECKING, Any

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

if TYPE_CHECKING:
    from odoo.addons.approval.models.approval_approver import ApprovalApprover
    from odoo.addons.approval.models.approval_category_step import (
        ApprovalCategoryStep,
    )
    from odoo.addons.approval_product.models.approval_request_line import (
        ApprovalRequestLine,
    )

_debug = DebugLog(__name__)


class ApprovalRequest(models.Model):
    _inherit = "approval.request"

    count_sale_order = fields.Integer(compute="_compute_count_sale_order")

    @api.depends("line_ids.sale_order_line_id")
    def _compute_count_sale_order(self) -> None:
        orders_from_mixin: dict[int, set[int]] = {}
        if self.ids:
            groups = (
                self.env["sale.order"]
                .sudo()
                ._read_group(
                    [("approval_request_id", "in", self.ids)],
                    ["approval_request_id"],
                    ["id:array_agg"],
                )
            )
            orders_from_mixin = {
                request.id: set(order_ids) for request, order_ids in groups
            }

        for request in self:
            orders = set(request.sudo().line_ids.sale_order_line_id.order_id.ids)
            orders |= orders_from_mixin.get(request._origin.id, set())
            request.count_sale_order = len(orders)

    def _check_confirm(self) -> None:
        super()._check_confirm()
        self._check_sale_type_has_product_lines()

    def action_approve(
        self,
        approver: ApprovalApprover | None = None,
        steps: ApprovalCategoryStep | None = None,
    ) -> dict[str, Any] | None:
        self._check_sale_type_has_product_lines()
        return super().action_approve(approver, steps)

    def _is_sale_target(self) -> bool:
        return self.target_model == "sale.order"

    def _get_target_line_field(self) -> str:
        if self._is_sale_target():
            return "sale_order_line_id"
        return super()._get_target_line_field()

    def _get_target_line_parent_field(self) -> str:
        if self._is_sale_target():
            return "order_id"
        return super()._get_target_line_parent_field()

    def _get_target_document_name(self) -> str:
        if self._is_sale_target():
            return self.env._("Sale Orders")
        return super()._get_target_document_name()

    def _get_target_document_label(self) -> str:
        if self._is_sale_target():
            return self.env._("sales order")
        return super()._get_target_document_label()

    def _is_target_rollback_enabled(self) -> bool:
        if self._is_sale_target():
            return True
        return super()._is_target_rollback_enabled()

    def _check_target_prerequisites(self, lines: ApprovalRequestLine) -> None:
        super()._check_target_prerequisites(lines)
        if not self._is_sale_target():
            return
        for line in lines:
            if not (line.partner_id or self.partner_id):
                _debug.logic(
                    "sale_target_refused",
                    request=self,
                    line=line,
                    reason="no_customer",
                )
                raise UserError(
                    self.env._(
                        "Customer not specified for line with product %s. "
                        "Please set a customer on the approval request or line.",
                        line.product_id.display_name,
                    ),
                )

    def _prepare_target_document_values(
        self, key: Any, lines: ApprovalRequestLine
    ) -> dict[str, Any]:
        if not self._is_sale_target():
            return super()._prepare_target_document_values(key, lines)
        return {
            "origin": self.name,
            "partner_id": key,
            "company_id": self.company_id.id,
        }

    def _prepare_target_line_values(
        self,
        line: ApprovalRequestLine,
        key: Any,
        document: models.BaseModel,
        lines: ApprovalRequestLine,
    ) -> dict[str, Any]:
        if not self._is_sale_target():
            return super()._prepare_target_line_values(line, key, document, lines)
        return {
            "product_id": line.product_id.id,
            "product_qty": line.quantity,
            "price_unit": line.price_unit,
            "product_uom_id": line.product_uom_id.id,
            "name": line.description or line.product_id.display_name,
        }

    def action_create_sale_orders(self) -> dict[str, Any]:
        return self.action_create_target_documents()

    def action_view_sale_order(self) -> dict[str, Any]:
        return self.action_view_target_documents()

    def _get_all_sale_orders(self) -> models.BaseModel:
        return self._get_documents_of_model(
            "sale.order",
            "sale_order_line_id",
            "order_id",
        )

    def _check_withdraw_allowed(self) -> None:
        super()._check_withdraw_allowed()
        self._check_withdraw_blocked_by(
            self._get_all_sale_orders(),
            self.env._("sales order"),
        )

    def _get_sale_display_lines(
        self, limit: int | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        self.check_singleton()
        orders = self._get_all_sale_orders().sudo()
        product_lines = orders.line_ids.filtered(
            lambda line: not line.display_type and line.product_id,
        )
        omitted = 0
        if limit and len(product_lines) > limit:
            omitted = len(product_lines) - limit
            product_lines = product_lines[:limit]
        return [
            {
                "order": line.order_id.name or "",
                "product": line.product_id.display_name or "",
                "description": line.name or "",
                "quantity": line.product_qty,
                "uom": line.product_uom_id.name or "",
                "price_unit": line.price_unit,
                "subtotal": line.price_subtotal,
                "currency": line.order_id.currency_id.symbol or "",
            }
            for line in product_lines
        ], omitted

    def _check_sale_type_has_product_lines(self) -> None:
        self.check_singleton()
        if self.target_model == "sale.order":
            if not self.line_ids:
                raise UserError(
                    self.env._(
                        "You cannot confirm an empty sale request. "
                        "Please add product lines.",
                    ),
                )
            if self.has_product == "no":
                raise UserError(
                    self.env._(
                        "This approval category is configured to create sale orders "
                        "but does not have product lines enabled. "
                        "Please contact your administrator.",
                    ),
                )
