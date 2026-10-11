from datetime import date as date_type

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.tools import frozendict

SHORT_TERM_HORIZON = relativedelta(years=1)


class AccountLoanLine(models.Model):
    _name = "account.loan.line"
    _description = "Loan Line"
    _order = "date, id"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False, hierarchy="parent_of"),
        }
    )

    period_number = fields.Integer(
        string="#",
        compute="_compute_schedule_position",
        store=True,
    )
    loan_id = fields.Many2one(
        comodel_name="account.loan",
        index=True,
        required=True,
        ondelete="cascade",
    )
    loan_name = fields.Char(related="loan_id.name")
    loan_state = fields.Selection(related="loan_id.state")
    loan_date = fields.Date(related="loan_id.date")
    loan_asset_group_id = fields.Many2one(related="loan_id.asset_group_id")
    active = fields.Boolean(related="loan_id.active")
    company_id = fields.Many2one(related="loan_id.company_id")
    currency_id = fields.Many2one(related="company_id.currency_id")
    date = fields.Date(required=True)
    principal = fields.Monetary()
    interest = fields.Monetary()
    payment = fields.Monetary(
        compute="_compute_payment",
        store=True,
    )
    outstanding_balance = fields.Monetary(
        compute="_compute_schedule_position",
        store=True,
        help="Principal still owed once this line has been paid.",
    )
    long_term_theoretical_balance = fields.Monetary(
        string="Long-Term",
        compute="_compute_schedule_position",
        store=True,
        help="Principal falling due more than a year after this line.",
    )
    short_term_theoretical_balance = fields.Monetary(
        string="Short-Term",
        compute="_compute_schedule_position",
        store=True,
        help="Principal falling due within a year of this line.",
    )
    generated_move_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="generating_loan_line_id",
        string="Generated Entries",
        copy=False,
        readonly=True,
        help="Entries that we generated from this loan line",
    )
    is_payment_move_posted = fields.Boolean(compute="_compute_is_payment_move_posted")

    @api.depends("principal", "interest")
    def _compute_payment(self) -> None:
        for line in self:
            line.payment = line.principal + line.interest

    @api.depends(
        "loan_id.amount_borrowed", "loan_id.line_ids.date", "loan_id.line_ids.principal"
    )
    def _compute_schedule_position(self) -> None:
        self.period_number = 0
        self.outstanding_balance = 0.0
        self.long_term_theoretical_balance = 0.0
        self.short_term_theoretical_balance = 0.0
        for loan in self.loan_id:
            schedule = loan._get_ordered_lines()
            dates = [line.date or date_type.max for line in schedule]
            principals = [line.principal for line in schedule]
            count = len(schedule)

            suffix_totals = [0.0] * (count + 1)
            for index in range(count - 1, -1, -1):
                suffix_totals[index] = suffix_totals[index + 1] + principals[index]

            rounding = (
                loan.currency_id.round if loan.currency_id else lambda value: value
            )
            remaining = loan.amount_borrowed
            boundary = 0
            for index, line in enumerate(schedule):
                remaining -= principals[index]
                horizon = dates[index] + SHORT_TERM_HORIZON
                boundary = max(boundary, index + 1)
                while boundary < count and dates[boundary] <= horizon:
                    boundary += 1
                line.period_number = index + 1
                line.outstanding_balance = rounding(remaining)
                line.short_term_theoretical_balance = rounding(
                    suffix_totals[index + 1] - suffix_totals[boundary]
                )
                line.long_term_theoretical_balance = rounding(suffix_totals[boundary])

    @api.depends("generated_move_ids.state")
    def _compute_is_payment_move_posted(self) -> None:
        for line in self:
            payment_moves = line.generated_move_ids.filtered("is_loan_payment_move")
            if len(payment_moves) > 1 and any(
                move.reversal_move_ids for move in payment_moves
            ):
                payment_moves = payment_moves.filtered(
                    lambda move: not move.reversal_move_ids
                )
            line.is_payment_move_posted = any(
                move.state == "posted" for move in payment_moves
            )
