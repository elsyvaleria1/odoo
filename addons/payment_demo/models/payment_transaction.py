from odoo import fields, models

from odoo.addons.payment.logging import get_payment_logger

_logger = get_payment_logger(__name__)


class PaymentTransaction(models.Model):
    _inherit = "payment.transaction"

    capture_manually = fields.Boolean(related="provider_id.capture_manually")

    def action_demo_set_done(self) -> None:
        self.check_singleton()
        if self.provider_code != "demo":
            return

        payment_data = {"reference": self.reference, "simulated_state": "done"}
        self._process("demo", payment_data)

    def action_demo_set_canceled(self) -> None:
        self.check_singleton()
        if self.provider_code != "demo":
            return

        payment_data = {"reference": self.reference, "simulated_state": "cancel"}
        self._process("demo", payment_data)

    def action_demo_set_error(self) -> None:
        self.check_singleton()
        if self.provider_code != "demo":
            return

        payment_data = {"reference": self.reference, "simulated_state": "error"}
        self._process("demo", payment_data)

    def _send_payment_request(self):
        if self.provider_code != "demo":
            return super()._send_payment_request()

        simulated_state = self.token_id.demo_simulated_state
        payment_data = {"reference": self.reference, "simulated_state": simulated_state}
        self._process("demo", payment_data)
        return None

    def _send_capture_request(self):
        if self.provider_code != "demo":
            return super()._send_capture_request()

        payment_data = {
            "reference": self.reference,
            "simulated_state": "done",
            "manual_capture": True,
        }
        self._process("demo", payment_data)
        return None

    def _send_void_request(self):
        if self.provider_code != "demo":
            return super()._send_void_request()

        payment_data = {"reference": self.reference, "simulated_state": "cancel"}
        self._process("demo", payment_data)
        return None

    def _send_refund_request(self):
        if self.provider_code != "demo":
            return super()._send_refund_request()

        payment_data = {"reference": self.reference, "simulated_state": "done"}
        self._process("demo", payment_data)
        return None

    def _extract_amount_data(self, payment_data) -> dict | None:
        if self.provider_code != "demo":
            return super()._extract_amount_data(payment_data)
        return None

    def _apply_updates(self, payment_data):
        if self.provider_code != "demo":
            return super()._apply_updates(payment_data)

        self.provider_reference = f"demo-{self.reference}"

        if self.tokenize:
            self._tokenize(payment_data)

        state = payment_data["simulated_state"]
        if state == "pending":
            self._set_pending()
        elif state == "done":
            if self.capture_manually and not payment_data.get("manual_capture"):
                self._set_authorized()
            else:
                self._set_done()
                if self.operation == "refund":
                    self.env["ir.cron"]._trigger_ref(
                        "payment.cron_post_process_payment_tx"
                    )
        elif state == "cancel":
            self._set_canceled()
        else:
            self._set_error(
                self.env._("You selected the following demo payment status: %s", state)
            )
        return None

    def _extract_token_values(self, payment_data) -> dict:
        if self.provider_code != "demo":
            return super()._extract_token_values(payment_data)

        if self.state in ("done", "authorized"):
            return {}

        state = payment_data["simulated_state"]
        return {
            "payment_details": payment_data["payment_details"],
            "provider_ref": "fake provider reference",
            "demo_simulated_state": state,
        }
