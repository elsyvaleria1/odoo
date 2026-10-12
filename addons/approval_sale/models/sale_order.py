from datetime import datetime

from odoo import models
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _name = "sale.order"
    _inherit = ["sale.order", "mixin.approval.document"]
    _access_anchors = frozendict(
        {
            "owner": "approval_pending_user_ids",
        }
    )

    def _get_approval_field_prefix(self) -> str:
        return "so"

    def _get_approval_document_label(self) -> str:
        return self.env._("Sales Order")

    def _get_approval_partner_label(self) -> str:
        return self.env._("Customer")

    def _get_approval_category_type(self) -> str:
        return "sale"

    def _get_approval_manager_group(self) -> str:
        return "sale.group_sale_manager"

    def _get_approval_subtype(self, state: str) -> str:
        return f"approval_sale.mt_sale_{state}"

    def _get_approval_config_menu(self) -> str:
        return self.env._("Sales → Configuration → Approval Types")

    def _get_approval_deadline_date(self) -> datetime | None:
        return self.date_commitment or self.date_planned or None

    def _get_approval_reference(self) -> str | None:
        return self.client_order_ref or None

    def action_cancel(self) -> bool:
        result = super().action_cancel()
        self._refuse_pending_approval()
        return result

    def _is_lock_required(self) -> bool:
        self.check_singleton()
        if super()._is_lock_required():
            return True
        locked = self._is_locked_by_approval()
        _debug.logic("approval_lock_check", order=self, locked=locked)
        return bool(locked)
