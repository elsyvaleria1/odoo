from odoo import models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class PaymentToken(models.Model):
    _inherit = "payment.token"

    def _handle_archiving(self) -> None:
        super()._handle_archiving()

        linked_subscriptions = self.env["sale.order"].search(
            [("payment_token_id", "in", self.ids)]
        )
        _debug.lifecycle(
            "subscription_tokens_voided",
            tokens=self,
            subscriptions=linked_subscriptions,
        )
        linked_subscriptions.write({"payment_token_id": None})

    def _get_available_tokens(
        self, providers_ids, partner_id, is_subscription=False, **kwargs
    ):
        if not is_subscription:
            _debug.logic("available_tokens", by="payment_default")
            return super()._get_available_tokens(providers_ids, partner_id, **kwargs)

        partner = self.env["res.partner"].browse(partner_id)
        _debug.logic("available_tokens", by="commercial_partner_tree", partner=partner)
        return (
            self.env["payment.token"]
            .sudo()
            .search(
                [
                    ("provider_id", "in", providers_ids),
                    ("partner_id", "child_of", partner.commercial_partner_id.id),
                ]
            )
        )

    def get_linked_records_info(self):
        res = super().get_linked_records_info()
        subscriptions = self.env["sale.order"].search(
            [("payment_token_id", "=", self.id), ("require_payment", "=", True)]
        )
        for sub in subscriptions:
            res.append(
                {
                    "description": subscriptions._description,
                    "id": sub.id,
                    "name": sub.name,
                    "url": sub.get_portal_url(),
                    "active_subscription": sub.subscription_state
                    in ["3_progress", "4_paused"],
                }
            )
        _debug.perf.count(
            "token_linked_subscriptions", token=self, subscriptions=subscriptions
        )
        return res
