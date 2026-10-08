from odoo import fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardPosSessionCloseUnbalanced(models.TransientModel):
    _name = "wizard.pos.session.close.unbalanced"
    _description = "Close Session Wizard"

    amount_to_balance = fields.Float(string="Amount to balance")
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Destination account",
    )
    account_readonly = fields.Boolean(string="Destination account is readonly")
    message = fields.Text(string="Information message")

    def action_close_session(self):
        self.check_singleton()
        active_model = self.env.context.get("active_model")
        if active_model and active_model != "pos.session":
            raise UserError(self.env._("Select exactly one session to close."))
        session = self.env["pos.session"].browse(self.env.context.get("active_ids"))
        if len(session) != 1 or not session.exists():
            raise UserError(self.env._("Select exactly one session to close."))
        account = self.account_id
        # account_readonly only locks the field in the view
        if not session.has_access("choose_balancing_account"):
            account = session._get_balancing_account()
        _debug.lifecycle(
            "session_force_close",
            session=session,
            balance=self.amount_to_balance,
            requested_account=self.account_id,
            account=account,
        )
        return session.action_pos_session_closing_control(
            account,
            self.amount_to_balance,
            {
                int(payment_method_id): diff
                for payment_method_id, diff in (
                    self.env.context.get("bank_payment_method_diffs") or {}
                ).items()
            },
        )
