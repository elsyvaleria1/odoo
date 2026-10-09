import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    @api.model
    def _load_pos_self_data_domain(self, data, config):
        domain = super()._load_pos_self_data_domain(data, config)
        if config.self_ordering_mode == "kiosk":
            domain = Domain.OR(
                [
                    [
                        ("use_payment_terminal", "=", "qfpay"),
                        ("id", "in", config.payment_method_ids.ids),
                    ],
                    domain,
                ]
            )
        return domain

    @api.model
    def _qfpay_handle_webhook(self, config, data, uuid):
        if config.self_ordering_mode != "kiosk":
            return super()._qfpay_handle_webhook(config, data, uuid)

        if data.get("notify_type") != "payment":
            return None

        order = self.env["pos.order"].search([("uuid", "=", uuid)], limit=1)
        if not order:
            return None
        if data["status"] != "1":
            order._send_payment_result("fail")
            return None
        try:
            with self.env.cr.savepoint():
                paid = order._add_kiosk_terminal_payment(
                    self,
                    {
                        "payment_date": fields.Datetime.now(),
                        "payment_ref_no": data["chnlsn"],
                        "transaction_id": data["syssn"],
                    },
                )
        except UserError as error:
            _logger.warning("QFPay notification for %s refused: %s", order.uuid, error)
            return None
        if paid:
            order._send_payment_result("Success")
        return None
