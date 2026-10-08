from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)


class AccountReturnPayment(models.Model):
    _name = "account.return.payment"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("return_id.company_ids", shared=False),
        }
    )
    _inherit = ["mixin.mail.thread", "mixin.mail.activity"]
    _description = "Tax Return Payment"
    _order = "id desc"
    _check_company_auto = True

    return_id = fields.Many2one(
        comodel_name="account.return",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="return_id.company_id",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        required=True,
    )
    reference = fields.Char(
        tracking=True,
        help="The reference the authority expects with the money: a structured "
        "communication, a payment reference number, a capture line.",
    )
    amount = fields.Monetary(
        currency_field="currency_id",
        tracking=True,
    )
    date_due = fields.Date(
        string="Reference Valid Until",
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Authority",
    )
    bank_account_id = fields.Many2one(
        comodel_name="res.partner.bank.account",
        string="Authority Bank Account",
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Paid From",
        domain="[('type', 'in', ('bank', 'cash', 'credit'))]",
        check_company=True,
    )
    payment_id = fields.Many2one(
        comodel_name="account.payment",
        index="btree_not_null",
        copy=False,
        readonly=True,
    )
    bank_receipt_ref = fields.Char(
        string="Bank Receipt",
        tracking=True,
        help="The bank's own reference for the transfer, as printed on its receipt.",
    )
    is_instructed = fields.Boolean(copy=False)
    is_cancelled = fields.Boolean(copy=False)
    is_expired = fields.Boolean(
        copy=False,
        help="The reference lapsed unpaid; the authority will not take money against it.",
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("instructed", "Instructed"),
            ("in_process", "In Process"),
            ("paid", "Paid"),
            ("expired", "Expired"),
            ("cancelled", "Cancelled"),
        ],
        compute="_compute_state",
        store=True,
        tracking=True,
    )

    @api.depends(
        "is_cancelled",
        "is_expired",
        "is_instructed",
        "payment_id.state",
        "return_id.state",
    )
    def _compute_state(self) -> None:
        for record in self:
            if record.is_cancelled or record.payment_id.state in (
                "canceled",
                "rejected",
            ):
                record.state = "cancelled"
            elif record.payment_id.state == "paid" or (
                not record.payment_id and record.return_id.state == "paid"
            ):
                record.state = "paid"
            elif record.payment_id.state == "in_process":
                record.state = "in_process"
            elif record.is_expired:
                record.state = "expired"
            elif record.is_instructed:
                record.state = "instructed"
            else:
                record.state = "draft"

    def _get_settlement_account(self):
        self.check_singleton()
        return self.return_id.type_id.with_company(
            self.company_id
        ).settlement_account_id

    def _prepare_payment_vals(self) -> dict:
        self.check_singleton()
        return {
            "payment_type": "outbound",
            "partner_type": "supplier",
            "partner_id": self.partner_id.id,
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "journal_id": self.journal_id.id,
            "company_id": self.company_id.id,
            "date": fields.Date.context_today(self),
            "memo": self.reference or self.return_id.name,
            "destination_account_id": self._get_settlement_account().id,
        }

    def _check_can_create_payment(self) -> None:
        self.check_singleton()
        if self.payment_id:
            raise UserError(
                self.env._("This payment already has its accounting payment.")
            )
        if self.state == "cancelled":
            raise UserError(self.env._("A cancelled payment cannot be paid."))
        if self.state == "expired" or (
            self.date_due and self.date_due < fields.Date.context_today(self)
        ):
            raise UserError(
                self.env._(
                    "The reference %(reference)s lapsed on %(date)s; get a new one from the "
                    "authority.",
                    reference=self.reference or self.display_name,
                    date=self.date_due,
                )
            )
        if not self._get_settlement_account():
            raise UserError(
                self.env._(
                    "The return type %(type)s has no settlement account for %(company)s.",
                    type=self.return_id.type_id.display_name,
                    company=self.company_id.display_name,
                )
            )
        if not self.partner_id:
            raise UserError(self.env._("Set the authority the tax is paid to."))
        if not self.journal_id:
            raise UserError(self.env._("Choose the journal the payment is made from."))
        if self.currency_id.compare_amounts(self.amount, 0) <= 0:
            raise UserError(self.env._("Only a positive amount can be paid."))

    @_debug.perf.timed
    def action_create_payment(self) -> None:
        _debug.lifecycle("action_create_payment", records=self)
        self.check_singleton()
        self._check_can_create_payment()
        payment = self.env["account.payment"].create(self._prepare_payment_vals())
        payment.action_post()
        self.payment_id = payment
        self._reconcile_with_settlement()

    def _reconcile_with_settlement(self) -> None:
        self.check_singleton()
        account = self._get_settlement_account()
        lines = (
            self.payment_id.move_id.line_ids | self.return_id._get_settlement_lines()
        ).filtered(
            lambda line: (
                line.account_id == account
                and line.company_id == self.company_id
                and not line.reconciled
            )
        )
        _debug.pipeline(
            "settlement_reconciled",
            records=self,
            payment=self.payment_id,
            lines=lines,
        )
        if lines.filtered("debit") and lines.filtered("credit"):
            lines.reconcile()

    def action_mark_instructed(self) -> None:
        self.is_instructed = True

    def action_cancel(self) -> None:
        if self.payment_id.filtered(
            lambda payment: payment.state not in ("draft", "canceled")
        ):
            raise UserError(
                self.env._(
                    "Cancel or reset the accounting payment before cancelling this payment."
                )
            )
        self.is_cancelled = True

    @api.model
    def _cron_expire_references(self) -> None:
        lapsed = self.search(
            [
                ("date_due", "<", fields.Date.context_today(self)),
                ("state", "in", ("draft", "instructed")),
            ]
        )
        _debug.pipeline("references_expired", records=lapsed)
        lapsed.is_expired = True
        for record in lapsed:
            record.activity_schedule(
                "mail.mail_activity_data_todo",
                summary=self.env._("Payment reference lapsed"),
                note=self.env._(
                    "%(reference)s for %(name)s lapsed unpaid; get a new reference from "
                    "the authority.",
                    reference=record.reference or record.display_name,
                    name=record.return_id.display_name,
                ),
                user_id=record.return_id.create_uid.id or self.env.uid,
            )
