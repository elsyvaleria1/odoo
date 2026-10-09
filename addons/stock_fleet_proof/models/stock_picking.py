from collections import defaultdict
from typing import Any

from odoo import models
from odoo.tools import float_repr

CONFIRMATION_PURPOSE = "stock.picking.delivery"


class StockPicking(models.Model):
    _name = "stock.picking"
    _inherit = ["stock.picking", "mixin.proof.confirmation"]

    def _has_delivery_proof(self):
        return super()._has_delivery_proof() or self._is_confirmation_current()

    def _action_done(self, *, cancel_backorder=False):
        res = super()._action_done(cancel_backorder=cancel_backorder)
        # a customer who confirmed at the door what was delivered is not asked
        # again; one who confirmed more than left is
        self.filtered(
            lambda picking: picking.state == "done" and picking._is_customer_delivery()
        )._ask_confirmation()
        return res

    def _is_customer_delivery(self) -> bool:
        self.check_singleton()
        # a return to a vendor leaves by the delivery type too, to no customer
        return bool(
            self.partner_id and not self.return_id and self._requires_delivery_proof()
        )

    def _is_confirmation_askable(self) -> bool:
        self.check_singleton()
        return self.state != "cancel"

    def _get_confirmation_partner(self) -> models.BaseModel:
        self.check_singleton()
        if not self._is_customer_delivery():
            return self.env["res.partner"]
        return self.partner_id.commercial_partner_id

    def _get_confirmation_purpose(self) -> str:
        return CONFIRMATION_PURPOSE

    def _get_delivered_quantities(self) -> list[tuple[models.BaseModel, float]]:
        quantities = defaultdict(float)
        moves = self.move_ids.filtered(lambda move: move.state != "cancel")
        # what leaves: the moves picked when some are, all of them before then
        moves = moves.filtered("picked") or moves
        for move in moves:
            quantities[move.product_id] += move.product_uom_id._get_quantity_report(
                move.quantity, move.product_id.uom_id
            )
        return sorted(quantities.items(), key=lambda item: item[0].id)

    def _get_confirmation_facts(self) -> dict[str, Any]:
        self.check_singleton()
        return {
            "picking": self.id,
            "customer": self.partner_id.commercial_partner_id.id,
            "address": self.partner_id.id,
            "products": [
                [
                    product.id,
                    float_repr(quantity, product.uom_id._precision_digits()),
                    product.uom_id.name,
                ]
                for product, quantity in self._get_delivered_quantities()
            ],
            "origin": self.origin or None,
        }

    def _get_confirmation_summary(self) -> list[list[str]]:
        self.check_singleton()
        env = self.env
        summary = [
            [env._("Delivery"), self.name],
            [
                env._("Products"),
                "; ".join(
                    f"{product.display_name}: "
                    f"{float_repr(quantity, product.uom_id._precision_digits())} "
                    f"{product.uom_id.name}"
                    for product, quantity in self._get_delivered_quantities()
                ),
            ],
            [env._("Delivered to"), self.partner_id.display_name],
        ]
        if self.batch_id.driver_id:
            summary.append([env._("Driver"), self.batch_id.driver_id.name])
        if self.origin:
            summary.append([env._("Reference"), self.origin])
        return summary

    def _on_confirmation_asked(self, challenge: models.BaseModel) -> None:
        channels = self._get_confirmation_channels()
        self.message_post(
            body=self.env._(
                "The customer was asked to confirm this delivery on %(channels)s.",
                channels=", ".join(channels),
            )
            if channels
            else self.env._("No channel reaches the customer to confirm this delivery.")
        )

    def _on_confirmation_answered(self, evidence: models.BaseModel) -> None:
        sent_to = (evidence.payload or {}).get("sent_to") or "-"
        if evidence.verdict == "confirmed":
            self._post_customer_answer(
                self.env._(
                    "I confirm this delivery as it is (%(sent_to)s).", sent_to=sent_to
                )
            )
            # the customer's word is evidence: once, and as a reviewer's tick,
            # which a reviewer may take back
            if not self.delivery_proof_ok:
                self.with_privilege(
                    "stock_fleet_proof.privilege_accept_customer_confirmation",
                    reason="the customer confirmed the delivery as it is",
                ).delivery_proof_ok = True
            return
        reason = (evidence.payload or {}).get("reason") or ""
        self._post_customer_answer(
            self.env._(
                "This delivery is not right (%(sent_to)s). %(reason)s",
                sent_to=sent_to,
                reason=reason,
            )
        )
        responsible = self.user_id or self.batch_id.user_id
        if responsible:
            self.activity_schedule(
                act_type_xmlid="mail.mail_activity_data_todo",
                summary=self.env._("The customer disputes this delivery"),
                note=reason,
                user_id=responsible.id,
            )

    def _on_confirmation_comment(self, evidence: models.BaseModel, text: str) -> None:
        self._post_customer_answer(text)

    def _on_confirmation_expired(self) -> None:
        self.message_post(
            body=self.env._("The customer did not answer whether they received this.")
        )

    def _post_customer_answer(self, body: str) -> None:
        # the customer's own words, kept as a note in their name
        self.message_post(
            author_id=self.partner_id.commercial_partner_id.id,
            body=body,
            subtype_xmlid="mail.mt_note",
        )
