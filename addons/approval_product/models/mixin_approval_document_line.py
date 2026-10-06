from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class MixinApprovalDocumentLine(models.AbstractModel):
    _name = "mixin.approval.document.line"
    _description = "Approval Mixin for the Lines of Order-Like Documents"

    _APPROVAL_PROTECTED_LINE_FIELDS = frozenset(
        {
            "discount",
            "name",
            "order_id",
            "price_unit",
            "product_id",
            "product_qty",
            "product_uom_id",
            "tax_ids",
        },
    )

    approval_request_line_id = fields.Many2one(
        comodel_name="approval.request.line",
        index=True,
        copy=False,
        readonly=True,
        help="Link to the approval request line that created this order line",
    )

    @api.model_create_multi
    def create(self, vals_list):
        orders = self.env[self._fields["order_id"].comodel_name].browse(
            {vals["order_id"] for vals in vals_list if vals.get("order_id")},
        )
        self._check_approval_not_pending(orders)
        return super().create(vals_list)

    def write(self, vals):
        touched = self._APPROVAL_PROTECTED_LINE_FIELDS & vals.keys()
        if touched:
            orders = self.order_id
            if vals.get("order_id"):
                orders |= orders.browse(vals["order_id"])
            self._check_approval_not_pending(orders, touched)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_approval_pending(self) -> None:
        self._check_approval_not_pending(self.order_id)

    def _check_approval_not_pending(self, orders, touched=None) -> None:
        if self.env.su:
            return

        blocked = orders.filtered(
            lambda order: order.approval_state == "pending",
        )
        if not blocked:
            return

        _debug.logic(
            "line_change_refused",
            orders=blocked,
            fields=",".join(sorted(touched)) if touched else "add_or_remove",
        )
        if touched:
            raise UserError(
                self.env._(
                    "Cannot modify %(fields)s on a line while the order's "
                    "approval is pending — approvers are deciding on the "
                    "current values. Withdraw or refuse the approval first."
                    "\n\nDocument: %(name)s",
                    fields=", ".join(sorted(touched)),
                    name=blocked[:1].display_name,
                ),
            )
        raise UserError(
            self.env._(
                "Cannot add or remove lines while the order's approval is "
                "pending — approvers are deciding on the current values. "
                "Withdraw or refuse the approval first.\n\nDocument: %(name)s",
                name=blocked[:1].display_name,
            ),
        )
