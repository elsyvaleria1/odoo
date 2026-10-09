from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog

_debug = DebugLog(__name__)


class WizardAccountReturnPay(models.TransientModel):
    _name = "wizard.account.return.pay"
    _description = "Returns Generic Payment Wizard"

    company_id = fields.Many2one(comodel_name="res.company")
    # compute_sudo=False on both: a related field is privileged by default
    # (coding_guidelines.rst 10.5), and bank_account_id is a plain many2one the user
    # sets, so the default would hand back the IBAN of any bank account in the
    # database -- including ones the reader's access domain hides.
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        related="bank_account_id.partner_id",
        compute_sudo=False,
    )
    acc_number = fields.Char(
        related="bank_account_id.acc_number",
        string="IBAN",
        compute_sudo=False,
    )
    # No check_company= here on purpose: this model does not set _check_company_auto,
    # so the flag would enforce nothing while reading as though it did. The reader's
    # own access domain is what scopes this now, via compute_sudo=False above.
    bank_account_id = fields.Many2one(comodel_name="res.partner.bank.account")
    communication = fields.Char(
        compute="_compute_communication",
        store=True,
        readonly=False,
    )

    amount_to_pay = fields.Monetary(
        compute="_compute_amount_to_pay",
        store=True,
        readonly=False,
    )
    is_recoverable = fields.Boolean(
        compute="_compute_is_recoverable",
        readonly=False,
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="return_id.amount_to_pay_currency_id",
    )
    return_id = fields.Many2one(
        comodel_name="account.return",
        required=True,
    )
    has_settlement = fields.Boolean(compute="_compute_has_settlement")
    has_single_settlement = fields.Boolean(compute="_compute_has_settlement")
    can_pay_from_journal = fields.Boolean(
        compute="_compute_has_settlement",
        help="A payment from a journal settles the return: on its one settlement "
        "account, or on each tax's account when it settles per concept.",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Paid From",
        domain="[('type', 'in', ('bank', 'cash', 'credit')), ('company_id', '=', company_id)]",
    )

    @_debug.perf.timed
    def _generate_communication(self):
        return False

    @api.depends("return_id")
    def _compute_amount_to_pay(self) -> None:
        for wizard in self:
            wizard.amount_to_pay = wizard.return_id.total_amount_to_pay

    @api.depends("amount_to_pay")
    def _compute_is_recoverable(self) -> None:
        for wizard in self:
            result = wizard.currency_id.compare_amounts(wizard.amount_to_pay, 0)
            wizard.is_recoverable = result in (-1, 0)

    @api.depends("return_id")
    def _compute_has_settlement(self) -> None:
        for wizard in self:
            wizard.has_settlement = bool(wizard.return_id._get_settlement_lines())
            wizard.has_single_settlement = (
                wizard.has_settlement
                and wizard.return_id._has_single_settlement_account()
            )
            wizard.can_pay_from_journal = wizard.has_single_settlement or (
                wizard.has_settlement
                and bool(wizard.return_id.type_id.settle_per_concept)
            )

    @api.depends("company_id")
    def _compute_communication(self) -> None:
        for wizard in self:
            wizard.communication = wizard._generate_communication()

    def _prepare_return_payment_vals(self) -> dict:
        self.check_singleton()
        return {
            "return_id": self.return_id.id,
            "currency_id": self.currency_id.id,
            "amount": self.amount_to_pay,
            "reference": self.communication or False,
            "partner_id": (
                self.return_id.type_id.payment_partner_id or self.partner_id
            ).id,
            "bank_account_id": self.bank_account_id.id,
            "journal_id": self.journal_id.id,
        }

    @_debug.perf.timed
    def action_mark_as_paid(self):
        _debug.lifecycle("action_mark_as_paid", records=self)
        self.check_singleton()
        if self.has_settlement:
            raise UserError(
                self.env._(
                    "This return is paid when its settlement line is reconciled with money "
                    "that left the bank: create the payment, or reconcile the bank "
                    "statement line with it."
                )
            )
        return self.return_id._action_finalize_payment()

    @_debug.perf.timed
    def action_create_payment(self) -> dict:
        _debug.lifecycle("action_create_payment", records=self)
        self.check_singleton()
        return_payment = self.env["account.return.payment"].create(
            self._prepare_return_payment_vals()
        )
        return_payment.action_create_payment()
        return {
            "type": "ir.actions.client",
            "tag": "action_return_refresh",
            "params": {
                "next_action": {"type": "ir.actions.act_window_close"},
                "return_ids": self.return_id.ids,
            },
        }

    @_debug.perf.timed
    def action_record_reference(self) -> dict:
        _debug.lifecycle("action_record_reference", records=self)
        self.check_singleton()
        self.env["account.return.payment"].create(
            {**self._prepare_return_payment_vals(), "is_instructed": True}
        )
        return {
            "type": "ir.actions.client",
            "tag": "action_return_refresh",
            "params": {
                "next_action": {"type": "ir.actions.act_window_close"},
                "return_ids": self.return_id.ids,
            },
        }

    @_debug.perf.timed
    def action_send_email_instructions(self):
        _debug.lifecycle("action_send_email_instructions", records=self)
        self.check_singleton()
        self.env["account.return.payment"].create(
            {**self._prepare_return_payment_vals(), "is_instructed": True}
        )
        template = self.env.ref(
            "account.email_template_generic_tax_instructions",
            raise_if_not_found=False,
        )
        return self.return_id.action_send_email_instructions(self, template)
