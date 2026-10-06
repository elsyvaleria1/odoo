from odoo import api, fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    credit_verdict_outcome = fields.Selection(
        selection=[
            ("allow", "Allowed"),
            ("warn", "Warning"),
            ("approve", "Needs authorization"),
            ("block", "Blocked"),
        ],
        compute="_compute_credit_verdict",
    )
    credit_verdict_message = fields.Text(compute="_compute_credit_verdict")

    def _credit_order(self):
        """The order this delivery ships, read whoever opens or validates it.

        :rtype: sale.order
        """
        # a branch's warehouse keeper may also sell, as a seller reading only
        # their own orders: a colleague's delivery weighs its credit all the same
        self.check_singleton()
        return self.with_privilege(
            "account_credit.privilege_credit_delivery",
            reason="a delivery weighs the credit of the order it ships",
        ).sale_id

    def _is_credit_delivery(self) -> bool:
        self.check_singleton()
        order = self._credit_order()
        return bool(
            self.picking_type_code == "outgoing"
            and order
            and not order._is_immediate_payment()
        )

    def _credit_verdict(self):
        self.check_singleton()
        if not self._is_credit_delivery():
            return None
        order = self._credit_order()
        profile = (
            self.env["credit.profile"]
            .sudo()
            .with_company(self.company_id)
            ._for_partner(order.partner_id, company=self.company_id)
        )
        if not profile:
            return None
        return profile._evaluate(
            "picking",
            immediate=False,
            term_days=profile._term_days(order.payment_term_id),
        )

    @api.depends("sale_id", "picking_type_code", "state")
    def _compute_credit_verdict(self) -> None:
        for picking in self:
            verdict = (
                picking._credit_verdict()
                if picking.state not in ("done", "cancel")
                else None
            )
            picking.credit_verdict_outcome = verdict.outcome if verdict else False
            picking.credit_verdict_message = verdict.message() if verdict else False

    def _check_before_validation(self, batch=None):
        super()._check_before_validation(batch=batch)
        if self.env["credit.profile"]._credit_override():
            return
        for picking in self:
            if not picking._is_credit_delivery():
                continue
            order = picking._credit_order()
            profile = (
                self.env["credit.profile"]
                .sudo()
                .with_company(picking.company_id)
                ._for_partner(order.partner_id, company=picking.company_id)
            )
            if not profile:
                continue
            _debug.logic("credit_delivery_check", picking=picking, order=order)
            profile._check_credit(
                "picking",
                immediate=False,
                term_days=profile._term_days(order.payment_term_id),
            )
