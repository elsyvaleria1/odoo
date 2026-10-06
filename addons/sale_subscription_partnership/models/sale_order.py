from odoo import models
from odoo.libs.debug_log import DebugLog

from odoo.addons.sale_subscription.models.sale_order import SUBSCRIPTION_PROGRESS_STATE

_debug = DebugLog(__name__)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _action_cancel(self):
        res = super()._action_cancel()
        self._remove_partnership()
        return res

    def set_close(self, *args, **kwargs):
        res = super().set_close(*args, **kwargs)
        self._remove_partnership()
        return res

    def _remove_partnership(self):
        for so in self:
            if so.commercial_partner_id.grade_id != so.assigned_grade_id:
                _debug.logic(
                    "partnership_removal_skipped",
                    order=so,
                    partner_grade=so.commercial_partner_id.grade_id or None,
                    assigned_grade=so.assigned_grade_id or None,
                )
                continue
            partner_id = so.commercial_partner_id.sudo()
            _debug.lifecycle(
                "partnership_removed",
                order=so,
                partner=partner_id,
                grade=so.assigned_grade_id,
            )
            partner_id.grade_id = False
            if (
                partner_id.specific_property_product_pricelist
                == so.assigned_grade_id.default_pricelist_id
            ):
                _debug.lifecycle(
                    "partnership_pricelist_reset",
                    order=so,
                    partner=partner_id,
                    pricelist=so.assigned_grade_id.default_pricelist_id,
                )
                partner_id.specific_property_product_pricelist = False

    def _confirm_renewal(self):
        res = super()._confirm_renewal()
        self._add_partnership()
        return res

    def set_open(self):
        res = super().set_open()
        if _debug.lifecycle.enabled:
            _debug.lifecycle(
                "partnership_added_on_open",
                orders=self.filtered(
                    lambda order: (
                        order.subscription_state in SUBSCRIPTION_PROGRESS_STATE
                    )
                ),
            )
        self.filtered(
            lambda order: order.subscription_state in SUBSCRIPTION_PROGRESS_STATE
        )._add_partnership()
        return res
