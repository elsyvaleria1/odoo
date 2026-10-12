from odoo import api, fields, models

from odoo.addons.payment import utils as payment_utils
from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    mandate_id = fields.Many2one(
        comodel_name="sdd.mandate",
        index=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        txs = super().create(vals_list)
        sepa_txs = txs.filtered(
            lambda t: (
                t.provider_code == "custom"
                and t.provider_id.custom_mode == "sepa_direct_debit"
                and t.token_id.sdd_mandate_id
            )
        )
        for tx in sepa_txs:
            tx.mandate_id = tx.token_id.sdd_mandate_id
        return txs

    def _prepare_provider_processing_values(self, processing_values):
        if (
            self.provider_id.custom_mode != "sepa_direct_debit"
            or self.operation == "online_token"
        ):
            return super()._prepare_provider_processing_values(processing_values)

        return {
            "access_token": payment_utils.generate_access_token(self.reference),
        }

    def _send_payment_request(self):
        if self.provider_id.custom_mode != "sepa_direct_debit":
            return super()._send_payment_request()

        mandate = self.token_id.sdd_mandate_id
        if not mandate:
            self._set_error(self.env._("The token is not linked to a mandate."))
            return None

        mandate._update_and_partition_state_by_validity()
        if mandate.state != "active":
            self._set_error(self.env._("The mandate is invalid."))
            return None

        self._process("sepa_direct_debit", {"reference": self.reference})
        return None

    def _apply_updates(self, payment_data):
        if self.provider_id.custom_mode != "sepa_direct_debit":
            return super()._apply_updates(payment_data)

        if self.operation in ("online_token", "offline"):
            self._set_done()
        return None

    def _set_done(self, **kwargs):
        confirmed_txs = super()._set_done(**kwargs)
        sepa_txs = confirmed_txs.filtered(
            lambda t: (
                t.provider_code == "custom"
                and t.provider_id.custom_mode == "sepa_direct_debit"
                and t.mandate_id
            )
        )
        for tx in sepa_txs:
            existing_token = self.env["payment.token"].search(
                [
                    ("provider_id", "=", tx.provider_id.id),
                    ("sdd_mandate_id", "=", tx.mandate_id.id),
                ],
                limit=1,
            )
            tx.token_id = (
                existing_token
                or tx.provider_id._sdd_create_token_for_mandate(
                    tx.partner_id, tx.mandate_id
                )
            )
            if tx.mandate_id.state == "draft":
                tx.mandate_id._confirm()
        return confirmed_txs

    def _get_communication(self):
        if self.provider_id.custom_mode != "sepa_direct_debit":
            return super()._get_communication()
        else:
            return self.reference

    def _create_payment(self, **extra_create_values):
        if self.provider_id.custom_mode != "sepa_direct_debit":
            return super()._create_payment(**extra_create_values)

        if self.operation in ("online_token", "offline"):
            mandate = self.token_id.sdd_mandate_id
        else:
            mandate = self.mandate_id

        payment_channel = (
            self.provider_id.journal_id.inbound_payment_channel_ids.filtered(
                lambda l: l.payment_provider_id == self.provider_id
            )
        )
        return super()._create_payment(
            payment_channel_id=payment_channel.id, sdd_mandate_id=mandate.id
        )
