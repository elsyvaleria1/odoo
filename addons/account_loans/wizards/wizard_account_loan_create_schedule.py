from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..lib import amortization


class WizardAccountLoanCreateSchedule(models.TransientModel):
    _name = "wizard.account.loan.create.schedule"
    _description = "Loan Compute Wizard"

    loan_id = fields.Many2one(
        comodel_name="account.loan",
        required=True,
    )
    currency_id = fields.Many2one(related="loan_id.currency_id")
    loan_amount = fields.Monetary(required=True)
    interest_rate = fields.Float(
        digits=(16, 4),
        default=1.0,
        required=True,
    )
    loan_term = fields.Integer(
        default=1,
        required=True,
    )
    start_date = fields.Date(
        default=fields.Date.context_today,
        required=True,
    )
    first_payment_date = fields.Date(
        string="First Payment",
        compute="_compute_first_payment_date",
        precompute=True,
        store=True,
        readonly=False,
        required=True,
    )
    payment_end_of_month = fields.Selection(
        selection=[
            ("end_of_month", "End of Month"),
            ("at_anniversary", "At Anniversary"),
        ],
        string="Payment",
        default="end_of_month",
        required=True,
    )
    compounding_method = fields.Selection(
        selection=[(name, name) for name in amortization.DAY_COUNT_CONVENTIONS],
        default="30E/360",
        required=True,
    )
    preview_line_ids = fields.One2many(
        comodel_name="wizard.account.loan.create.schedule.line",
        inverse_name="wizard_id",
        string="Amortization Schedule",
        compute="_compute_preview_line_ids",
    )

    @property
    def _uses_first_payment_date(self) -> bool:
        return self.payment_end_of_month == "at_anniversary"

    @api.constrains(
        "loan_amount",
        "interest_rate",
        "loan_term",
        "start_date",
        "first_payment_date",
        "payment_end_of_month",
    )
    def _check_schedule_inputs(self) -> None:
        for wizard in self:
            wizard._check_schedule_parameters()

    def _check_schedule_parameters(self) -> None:
        self.check_singleton()
        if self.loan_amount < 0:
            raise ValidationError(self.env._("Loan Amount must be positive"))
        if not 0 <= self.interest_rate <= 100:
            raise ValidationError(self.env._("Interest Rate must be between 0 and 100"))
        if self.loan_term < 1:
            raise ValidationError(self.env._("Loan Term must be at least one year"))
        if (
            self._uses_first_payment_date
            and self.first_payment_date
            and self.start_date
            and self.start_date + relativedelta(years=self.loan_term)
            < self.first_payment_date
        ):
            raise ValidationError(
                self.env._("The First Payment Date must be before the end of the loan.")
            )

    @api.onchange(
        "loan_amount",
        "interest_rate",
        "loan_term",
        "start_date",
        "first_payment_date",
        "payment_end_of_month",
    )
    def _onchange_preview(self) -> None:
        self._check_schedule_parameters()

    @api.depends("start_date")
    def _compute_first_payment_date(self) -> None:
        for wizard in self:
            wizard.first_payment_date = wizard.start_date and (
                wizard.start_date.replace(day=1) + relativedelta(months=1)
            )

    def _get_loan_payment_schedule(self):
        self.check_singleton()
        try:
            return amortization.generate(
                amount=self.loan_amount,
                annual_rate=self.interest_rate,
                years=self.loan_term,
                start_date=self.start_date,
                first_payment_date=self.first_payment_date
                if self._uses_first_payment_date
                else None,
                end_of_month=not self._uses_first_payment_date,
                convention=self.compounding_method,
            )
        except amortization.ScheduleError as error:
            raise UserError(str(error)) from error

    @api.depends(
        "loan_amount",
        "interest_rate",
        "loan_term",
        "start_date",
        "first_payment_date",
        "payment_end_of_month",
        "compounding_method",
    )
    def _compute_preview_line_ids(self) -> None:
        for wizard in self:
            if not (wizard.loan_amount and wizard.loan_term and wizard.start_date):
                wizard.preview_line_ids = [Command.clear()]
                continue
            wizard.preview_line_ids = [Command.clear()] + [
                Command.create(
                    {
                        "date": payment.date,
                        "principal": float(payment.principal),
                        "interest": float(payment.interest),
                        "payment": float(payment.total),
                        "balance": float(payment.balance),
                    }
                )
                for payment in wizard._get_loan_payment_schedule()
            ]

    def action_save(self):
        self.check_singleton()
        schedule = self._get_loan_payment_schedule()
        self.loan_id._clear_schedule()
        self.env["account.loan.line"].create(
            [
                {
                    "loan_id": self.loan_id.id,
                    "date": payment.date,
                    "principal": float(payment.principal),
                    "interest": float(payment.interest),
                }
                for payment in schedule
            ]
        )
        self.loan_id._sync_header_with_schedule()
        self.loan_id.date = self.start_date
        return self.loan_id._get_loan_action(self.loan_id.name, res_id=self.loan_id.id)
