from typing import Any

from odoo import fields, models
from odoo.tools import float_repr, format_date

CONFIRMATION_PURPOSE = "account.payment.collection"


class AccountPayment(models.Model):
    _name = "account.payment"
    _inherit = ["account.payment", "mixin.proof.confirmation"]

    def _is_customer_collection(self) -> bool:
        self.check_singleton()
        return bool(
            self.is_collection_custody and self.collector_id and self.partner_id
        )

    def action_post(self):
        res = super().action_post()
        self._get_customer_collections()._ask_confirmation()
        return res

    def action_draft(self):
        self._get_customer_collections()._withdraw_confirmation()
        return super().action_draft()

    def action_cancel(self):
        self._get_customer_collections()._withdraw_confirmation()
        return super().action_cancel()

    def _get_customer_collections(self) -> AccountPayment:
        return self.filtered(lambda payment: payment._is_customer_collection())

    def _send_collection_receipt(self) -> None:
        # the confirmation mail carries the receipt's figures and its link: a
        # customer it reached gets no second mail
        mailed = self.filtered(lambda payment: payment._is_confirmation_mailed())
        super(AccountPayment, self - mailed)._send_collection_receipt()

    def _is_confirmation_mailed(self) -> bool:
        self.check_singleton()
        challenge = self._get_confirmation_challenges().get(self.id)
        return bool(
            challenge
            and challenge.delivery_ids.filtered(
                lambda delivery: delivery.method_id.code == "email_confirm"
            )
        )

    def _get_confirmation_partner(self) -> models.BaseModel:
        self.check_singleton()
        if not self._is_customer_collection():
            return self.env["res.partner"]
        return self.partner_id

    def _get_confirmation_purpose(self) -> str:
        return CONFIRMATION_PURPOSE

    def _get_confirmation_facts(self) -> dict[str, Any]:
        self.check_singleton()
        return {
            "payment": self.id,
            "customer": self.partner_id.id,
            "amount": float_repr(self.amount, self.currency_id.decimal_places),
            "currency": self.currency_id.name,
            "date": fields.Date.to_string(self.date),
            "method": self.collection_method or None,
            "check_date": fields.Date.to_string(self.collection_check_date)
            if self.collection_check_date
            else None,
            "collector": self.collector_id.id,
        }

    def _get_confirmation_summary(self) -> list[list[str]]:
        self.check_singleton()
        env = self.env
        methods = dict(self._fields["collection_method"]._description_selection(env))
        summary = [
            [env._("Receipt"), self.name],
            [env._("Amount"), self.currency_id.format(self.amount)],
            [env._("Paid on"), format_date(env, self.date)],
            [env._("Paid in"), methods.get(self.collection_method, "")],
            [env._("Received by"), self.collector_id.name],
        ]
        if self.collection_check_date:
            summary.append(
                [env._("Check date"), format_date(env, self.collection_check_date)]
            )
        if self.memo:
            summary.append([env._("Reference"), self.memo])
        return summary

    def _get_confirmation_links(self) -> list[tuple[str, str]]:
        self.check_singleton()
        return [(self.env._("Your receipt"), self.get_collection_receipt_url())]

    def _on_confirmation_answered(self, evidence: models.BaseModel) -> None:
        payment = self._with_answer_privilege()
        sent_to = (evidence.payload or {}).get("sent_to") or "-"
        if evidence.verdict == "confirmed":
            payment._post_customer_answer(
                self.env._("I confirm this collection (%(sent_to)s).", sent_to=sent_to)
            )
            return
        reason = (evidence.payload or {}).get("reason") or ""
        payment._post_customer_answer(
            self.env._(
                "This collection is not right (%(sent_to)s). %(reason)s",
                sent_to=sent_to,
                reason=reason,
            )
        )
        payment._schedule_supervisor_activity(
            self.env._("The customer disputes this collection"), reason
        )

    def _on_confirmation_comment(self, evidence: models.BaseModel, text: str) -> None:
        self._with_answer_privilege()._post_customer_answer(text)

    def _post_customer_answer(self, body: str) -> None:
        # the customer's own words, kept as a note in their name
        self.message_post(
            author_id=self.partner_id.id,
            body=body,
            subtype_xmlid="mail.mt_note",
        )

    def _on_confirmation_expired(self) -> None:
        payment = self._with_answer_privilege()
        payment.message_post(
            body=self.env._("The customer did not answer whether they paid this.")
        )
        payment._schedule_supervisor_activity(
            self.env._("The customer did not confirm this collection"), ""
        )

    def _schedule_supervisor_activity(self, summary: str, note: str) -> None:
        supervisor = self.company_id.account_config_id.collection_supervisor_id
        if supervisor:
            self.activity_schedule(
                act_type_xmlid="mail.mail_activity_data_todo",
                summary=summary,
                note=note,
                user_id=supervisor.id,
            )

    def _with_answer_privilege(self) -> AccountPayment:
        # the answer reaches the collection as its collector, who asked: their
        # own collection is theirs to note it on
        return self.with_privilege(
            "account_collection.privilege_register_collection",
            reason="a collector's collection notes what its customer answered",
        )
