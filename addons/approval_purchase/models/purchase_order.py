from odoo import models
from odoo.tools import frozendict


class PurchaseOrder(models.Model):
    _name = "purchase.order"
    _inherit = ["purchase.order", "mixin.approval.document"]
    _access_anchors = frozendict(
        {
            "owner": "approval_pending_user_ids",
        }
    )

    def _get_approval_field_prefix(self) -> str:
        return "po"

    def _get_approval_document_label(self) -> str:
        return self.env._("Purchase Order")

    def _get_approval_partner_label(self) -> str:
        return self.env._("Vendor")

    def _get_approval_category_type(self) -> str:
        return "purchase"

    def _get_approval_manager_group(self) -> str:
        return "purchase.group_purchase_manager"

    def _get_approval_subtype(self, state: str) -> str:
        return f"approval_purchase.mt_purchase_{state}"

    def _get_approval_config_menu(self) -> str:
        return self.env._("Purchase → Configuration → Approval Types")

    def _get_approval_reference(self) -> str:
        return self.partner_ref

    def action_cancel(self) -> bool:
        result = super().action_cancel()
        self._refuse_pending_approval()
        return result

    def _is_lock_required(self) -> bool:
        self.check_singleton()
        if super()._is_lock_required():
            return True
        return bool(self._is_locked_by_approval())
