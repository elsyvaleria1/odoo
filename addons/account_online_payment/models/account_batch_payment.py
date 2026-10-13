from odoo import SUPERUSER_ID, api, fields, models

from odoo.addons.account.tools.structured_reference import (
    is_valid_structured_reference_for_country,
)

STATUSES = [
    ("uninitiated", "Uninitiated"),
    ("unsigned", "Unsigned"),
    ("pending", "Pending"),
    ("accepted", "Accepted"),
    ("canceled", "Canceled"),
    ("rejected", "Rejected"),
]


class AccountBatchPayment(models.Model):
    _inherit = "account.batch.payment"

    payment_identifier = fields.Char(
        string="Batch ID",
        readonly=True,
    )
    payment_online_status = fields.Selection(
        selection=STATUSES,
        string="PIS Status",
        default="uninitiated",
        readonly=True,
    )
    account_online_link_payments_enabled = fields.Boolean(
        compute="_compute_account_online_link_payments_enabled"
    )

    def initiate_payment(self):
        self.check_singleton()

        if self.payment_online_status == "unsigned" and self.state == "sent":
            self.check_online_payment_status()
            if self.payment_online_status != "unsigned":
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": self.env._("Payment already been signed"),
                        "message": self.env._(
                            "This payment might have already been signed. Refreshing the payment status..."
                        ),
                        "type": "warning",
                        "next": {
                            "type": "ir.actions.client",
                            "tag": "soft_reload",
                        },
                    },
                }
            return self._sign_payment()
        return self.with_context(xml_export=False).confirm_batch()

    def confirm_batch(self):
        if (
            self.payment_method_code != "sepa_ct"
            or not self.account_online_link_payments_enabled
            or self.env.context.get("xml_export")
        ):
            return super().confirm_batch()

        action = self._check_batch_validity()
        if (
            action
            and action.get("res_model") == "wizard.account.batch.payment.validate.error"
        ):
            return action

        account_online_link = self.journal_id.account_online_link_id
        data = self._prepare_payment_data()
        while True:
            response = account_online_link._get_odoo_fin(
                "/proxy/v1/initiate_payment", data
            )
            if not response.get("next_data"):
                break
            data["next_data"] = response["next_data"]

        if response.get("kyc_flow"):
            self.with_user(SUPERUSER_ID).message_post(
                body=self.env._("""
                This payment requires a KYC flow. As this process can take a few days, please use SEPA XML export in the meantime.
                You will be notified once the KYC flow is completed and you can proceed with the online payment.
            """)
            )
        else:
            self._send_after_validation()
            self.write(
                {
                    "payment_identifier": response.get("payment_identifier"),
                    "payment_online_status": response.get("payment_online_status"),
                }
            )

        return {
            "type": "ir.actions.act_url",
            "url": response.get("redirect_url"),
            "target": "_blank",
        }

    def check_online_payment_status(self):
        statuses = {}
        for batch in self:
            account_online_account = batch.journal_id.account_online_account_id
            data = {
                "payment_identifier": batch.payment_identifier,
                "account_id": account_online_account.online_identifier,
                "payment_type": "bulk",
            }

            while True:
                response = batch.journal_id.account_online_link_id._get_odoo_fin(
                    "/proxy/v1/get_payment_status", data
                )
                if not response.get("next_data"):
                    break
                data["next_data"] = response["next_data"]

            batch.payment_online_status = response.get("payment_online_status")
            statuses[batch.id] = batch.payment_online_status
        return statuses

    def export_batch_payment(self) -> None:
        to_be_exported = self.env["account.batch.payment"]

        for record in self:
            if (
                record.payment_method_code == "sepa_ct"
                and record.account_online_link_payments_enabled
                and not self.env.context.get("xml_export")
            ):
                continue
            to_be_exported += record

        super(AccountBatchPayment, to_be_exported).export_batch_payment()
        if any(
            payment.payment_online_status in {"pending", "accepted"}
            for payment in to_be_exported
        ):
            self.with_user(SUPERUSER_ID).message_post(
                body=self.env._(
                    "Please be aware that signed payments may have already been processed and sent to the bank."
                )
            )

    def _sign_payment(self) -> dict:
        self.check_singleton()

        account_online_link = self.journal_id.account_online_link_id
        data = {
            **self._prepare_payment_data(),
            "payment_identifier": self.payment_identifier,
        }

        while True:
            response = account_online_link._get_odoo_fin("/proxy/v1/sign_payment", data)

            if not response.get("next_data"):
                break
            data["next_data"] = response["next_data"]

        self.payment_online_status = response["payment_online_status"]
        self.payment_identifier = response["payment_identifier"]

        return {
            "type": "ir.actions.act_url",
            "url": response["redirect_url"],
            "target": "_blank",
        }

    def _cron_check_payment_status(self) -> None:
        self.env["account.batch.payment"].search(
            [
                ("state", "!=", "reconciled"),
                ("payment_method_code", "=", "sepa_ct"),
                ("journal_id.account_online_link_id.is_payment_activated", "=", "True"),
                ("payment_online_status", "in", ("unsigned", "pending")),
            ]
        ).check_online_payment_status()

    @api.depends("journal_id.account_online_link_id")
    def _compute_account_online_link_payments_enabled(self) -> None:
        for batch in self:
            batch.account_online_link_payments_enabled = (
                batch.journal_id.account_online_link_id.is_payment_enabled
            )

    def _prepare_payment_data(self) -> dict:
        self.check_singleton()

        payments = [
            {
                "amount": payment.amount,
                "account_number": payment.bank_account_id.sanitized_acc_number,
                "account_type": "IBAN",
                "creditor_name": payment.partner_id.name,
                "currency": payment.currency_id.display_name,
                "date": fields.Date.to_string(payment.date),
                "reference": payment.memo,
                "structured_reference": is_valid_structured_reference_for_country(
                    payment.memo,
                    (payment.bank_account_id.sanitized_acc_number or "")[:2],
                ),
                "end_to_end_uuid": payment.end_to_end_uuid,
            }
            for payment in self.payment_ids
        ]

        return {
            "account_id": self.journal_id.account_online_account_id.online_identifier,
            "batch_booking": self.iso20022_batch_booking,
            "date": fields.Date.to_string(self.date),
            "payment_type": "bulk",
            "payments": payments,
            "reference": self.name,
        }
