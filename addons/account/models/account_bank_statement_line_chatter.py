from dateutil.relativedelta import relativedelta

from odoo import fields, models
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    def _get_last_5_minutes_messages(self, body):
        self.check_singleton()
        return self.env["mail.message"].search(
            [
                ("model", "=", self.move_id._name),
                ("res_id", "=", self.move_id.id),
                ("author_id", "=", self.env.user.partner_id.id),
                ("create_date", ">=", fields.Datetime.now() - relativedelta(minutes=5)),
                ("body", "=", body),
            ],
            limit=1,
        )

    @_debug.perf.timed
    def _post_matching_note(self, body) -> None:
        _debug.lifecycle("_post_matching_note", records=self)
        self.check_singleton()
        if self._get_last_5_minutes_messages(body=body):
            return
        self.move_id.message_post(body=body, author_id=self.env.user.partner_id.id)

    @_debug.perf.timed
    def _post_matching_done_confirmation(self) -> None:
        _debug.lifecycle("_post_matching_done_confirmation", records=self)
        self.check_singleton()
        if not self.is_reconciled:
            return
        body = self.env._("Matching done")
        if reconcile_model := self.move_id.line_ids.reconcile_model_id:
            body += self.env._(
                " - %(reconcile_model_name)s",
                reconcile_model_name=", ".join(reconcile_model.mapped("name")),
            )
        self._post_matching_note(body)

    @_debug.perf.timed
    def _post_matching_unreconciled(self) -> None:
        _debug.lifecycle("_post_matching_unreconciled", records=self)
        self.check_singleton()
        if self.is_reconciled:
            return
        self._post_matching_note(self.env._("Matching unreconciled"))

    @_debug.perf.timed
    def _create_payment_with_move_from_invoice(self, move_id):
        return (
            self.env["wizard.account.move.line.pay"]
            .with_context(
                active_model="account.move",
                active_ids=move_id.ids,
                force_payment_move=True,
            )
            .create(
                {
                    "payment_date": self.date,
                }
            )
            ._create_payments()
        )

    @_debug.perf.timed
    def _reconcile_with_payments(self, payments, amls_to_create) -> None:
        self.check_singleton()
        _debug.pipeline(
            "payment_lines_prepared",
            stline=self,
            payments=payments,
            amls=len(amls_to_create),
        )
        self._add_move_line_to_statement_line_move(amls_to_create)
        if payments_to_validate := payments.filtered(
            lambda p: (
                not p.move_id
                and p.state in self.env["account.payment"]._valid_payment_states()
            )
        ):
            _debug.logic(
                "payments_validated", stline=self, payment=payments_to_validate
            )
            payments_to_validate.action_validate()
