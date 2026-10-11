from datetime import date as date_type
from typing import Any

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.libs.documents import canonical_mimetypes, mimetypes_for
from odoo.tools import float_compare, frozendict
from odoo.tools.misc import format_date

from .account_loan_line import SHORT_TERM_HORIZON
from .common import records_action

IMPORTABLE_MIMETYPES = canonical_mimetypes("csv") | mimetypes_for("xls", "ods", "xlsx")
IMPORTABLE_EXTENSIONS = ".csv,.ods,.xls,.xlsm,.xlsx"


class AccountLoan(models.Model):
    _name = "account.loan"
    _description = "Loan"
    _inherit = ["mixin.mail.thread"]
    _order = "date"

    _STATE_TRANSITIONS = {
        "draft": ("running", "closed", "cancelled"),
        "running": ("draft", "closed", "cancelled"),
        "closed": ("draft", "cancelled"),
        "cancelled": ("draft",),
    }
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", hierarchy="parent_of"),
        }
    )

    @api.model
    def default_get(self, fields):
        values = super().default_get(fields)
        configuration_fields = [
            "expense_account_id",
            "long_term_account_id",
            "short_term_account_id",
            "journal_id",
        ]
        if all(field not in fields for field in configuration_fields):
            return values
        latest_loan = self.search(
            [
                ("company_id", "=", self.env.company.id),
                *[(field, "!=", False) for field in configuration_fields],
            ],
            order="date desc, id desc",
            limit=1,
        )
        for field in configuration_fields:
            if latest_loan:
                values[field] = latest_loan[field].id
        return values

    name = fields.Char(
        index="trigram",
        required=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    active = fields.Boolean(default=True)
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("running", "Running"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
        ],
        string="Status",
        default="draft",
        required=True,
        tracking=True,
    )
    date = fields.Date(
        string="Loan Date",
        index="btree_not_null",
    )
    amount_borrowed = fields.Monetary(tracking=True)
    interest = fields.Monetary()
    duration = fields.Integer()
    skip_until_date = fields.Date(
        string="Skip until",
        help="Upon confirmation of the loan, Odoo will ignore the loan lines that are up to this date (included) and not create entries for them. "
        "This is useful if you have already manually created entries prior to the creation of this loan.",
    )

    long_term_account_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('account_type', '=', 'liability_non_current')]",
        check_company=True,
        tracking=True,
    )
    short_term_account_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('account_type', '=', 'liability_current')]",
        check_company=True,
        tracking=True,
    )
    expense_account_id = fields.Many2one(
        comodel_name="account.account",
        domain="[('account_type', 'in', ('expense', 'expense_depreciation'))]",
        check_company=True,
        tracking=True,
    )
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        domain="[('type', '=', 'general')]",
        check_company=True,
    )
    asset_group_id = fields.Many2one(
        comodel_name="account.asset.group",
        index=True,
        tracking=True,
    )
    loan_properties = fields.Properties(
        definition="journal_id.loan_properties_definition",
        string="Properties",
    )

    line_ids = fields.One2many(
        comodel_name="account.loan.line",
        inverse_name="loan_id",
        string="Loan Lines",
    )

    display_name = fields.Char(
        string="Loan name",
        store=True,
    )
    start_date = fields.Date(compute="_compute_start_end_date")
    end_date = fields.Date(compute="_compute_start_end_date")
    is_wrong_date = fields.Boolean(compute="_compute_is_wrong_date")
    amount_borrowed_difference = fields.Monetary(
        compute="_compute_amount_borrowed_difference"
    )
    interest_difference = fields.Monetary(compute="_compute_interest_difference")
    duration_difference = fields.Integer(compute="_compute_duration_difference")
    outstanding_balance = fields.Monetary(
        compute="_compute_outstanding_balance",
        aggregator="sum",
    )
    nb_posted_entries = fields.Integer(compute="_compute_nb_posted_entries")
    linked_assets_ids = fields.One2many(
        comodel_name="account.depreciation.board",
        compute="_compute_linked_assets",
    )
    count_linked_assets = fields.Count(count_of="linked_assets_ids")

    _check_company_auto = True

    @api.constrains("amount_borrowed", "interest", "duration")
    def _check_nonnegative_loan_terms(self) -> None:
        for loan in self:
            rounding = loan.currency_id.rounding
            if (
                float_compare(loan.amount_borrowed, 0.0, precision_rounding=rounding)
                < 0
            ):
                raise ValidationError(
                    self.env._("The amount borrowed must be positive")
                )
            if float_compare(loan.interest, 0.0, precision_rounding=rounding) < 0:
                raise ValidationError(self.env._("The interest must be positive"))
            if loan.duration < 0:
                raise ValidationError(self.env._("The duration must be positive"))

    def _get_ordered_lines(self):
        self.check_singleton()
        return self.line_ids.sorted(
            lambda line: (line.date or date_type.max, line.id or 0)
        )

    def _is_skipped(self, line) -> bool:
        self.check_singleton()
        return bool(self.skip_until_date) and line.date <= self.skip_until_date

    def _iter_schedule_windows(self):
        self.check_singleton()
        schedule = self._get_ordered_lines()
        dates = [line.date for line in schedule]
        count = len(schedule)
        boundary = 0
        for index, line in enumerate(schedule):
            horizon = dates[index] + SHORT_TERM_HORIZON
            boundary = max(boundary, index + 1)
            while boundary < count and dates[boundary] <= horizon:
                boundary += 1
            yield line, schedule[index + 1 : boundary]

    def _is_fully_repaid(self) -> bool:
        self.check_singleton()
        return bool(self.line_ids) and all(
            line.is_payment_move_posted or self._is_skipped(line)
            for line in self.line_ids
        )

    def _set_state(self, target) -> None:
        for loan in self:
            if loan.state == target:
                continue
            if target not in self._STATE_TRANSITIONS[loan.state]:
                raise UserError(
                    self.env._(
                        "A loan cannot go from %(current)s to %(target)s.",
                        current=loan.state,
                        target=target,
                    )
                )
            loan.state = target

    def _settle_state(self) -> None:
        for loan in self:
            loan._set_state("closed" if loan._is_fully_repaid() else "running")

    @api.depends("name", "start_date", "end_date")
    def _compute_display_name(self):
        for loan in self:
            if loan.name and loan.start_date and loan.end_date:
                start_date = format_date(self.env, loan.start_date, date_format="MM y")
                end_date = format_date(self.env, loan.end_date, date_format="MM y")
                loan.display_name = f"{loan.name}: {start_date} - {end_date}"
            else:
                loan.display_name = loan.name

    @api.depends("line_ids.date")
    def _compute_start_end_date(self) -> None:
        for loan in self:
            schedule = loan._get_ordered_lines()
            loan.start_date = schedule[0].date if schedule else False
            loan.end_date = schedule[-1].date if schedule else False

    @api.depends("date", "line_ids.date")
    def _compute_is_wrong_date(self) -> None:
        for loan in self:
            loan.is_wrong_date = not loan.date or any(
                date < loan.date for date in loan.line_ids.mapped("date")
            )

    @api.depends("amount_borrowed", "line_ids.principal", "currency_id")
    def _compute_amount_borrowed_difference(self) -> None:
        for loan in self:
            if loan.currency_id:
                loan.amount_borrowed_difference = (
                    loan.amount_borrowed
                    - loan.currency_id.round(sum(loan.line_ids.mapped("principal")))
                )
            else:
                loan.amount_borrowed_difference = 0

    @api.depends("interest", "line_ids.interest", "currency_id")
    def _compute_interest_difference(self) -> None:
        for loan in self:
            if loan.currency_id:
                loan.interest_difference = loan.interest - loan.currency_id.round(
                    sum(loan.line_ids.mapped("interest"))
                )
            else:
                loan.interest_difference = 0

    @api.depends("duration", "line_ids")
    def _compute_duration_difference(self) -> None:
        for loan in self:
            loan.duration_difference = loan.duration - len(loan.line_ids)

    @api.depends("line_ids.generated_move_ids.state")
    def _compute_nb_posted_entries(self) -> None:
        for loan in self:
            loan.nb_posted_entries = len(
                loan.line_ids.generated_move_ids.filtered(lambda m: m.state == "posted")
            )

    @api.depends(
        "amount_borrowed",
        "line_ids.principal",
        "line_ids.is_payment_move_posted",
        "skip_until_date",
    )
    def _compute_outstanding_balance(self) -> None:
        for loan in self:
            repaid = sum(
                line.principal
                for line in loan.line_ids
                if line.is_payment_move_posted or loan._is_skipped(line)
            )
            balance = loan.amount_borrowed - repaid
            loan.outstanding_balance = (
                loan.currency_id.round(balance) if loan.currency_id else balance
            )

    @api.depends("asset_group_id")
    def _compute_linked_assets(self) -> None:
        for loan in self:
            loan.linked_assets_ids = loan.asset_group_id.linked_asset_ids

    def _get_move_label(self, line, kind) -> str:
        self.check_singleton()
        period = format_date(self.env, line.date, date_format="MM/y")
        return f"{self.name} - {kind} {period}"

    def _prepare_payment_move_vals(self, line) -> dict:
        self.check_singleton()
        return {
            "company_id": self.company_id.id,
            "auto_post": "at_date",
            "generating_loan_line_id": line.id,
            "is_loan_payment_move": True,
            "date": line.date + relativedelta(day=31),
            "journal_id": self.journal_id.id,
            "ref": self._get_move_label(line, self.env._("Principal & Interest")),
            "line_ids": [
                Command.create(
                    {
                        "account_id": self.long_term_account_id.id,
                        "debit": line.principal,
                        "name": self._get_move_label(line, self.env._("Principal")),
                    }
                ),
                Command.create(
                    {
                        "account_id": self.short_term_account_id.id,
                        "credit": line.payment,
                        "name": f"{self._get_move_label(line, self.env._('Due'))} "
                        f"({self.env._('Principal')} {self.currency_id.format(line.principal)} + "
                        f"{self.env._('Interest')} {self.currency_id.format(line.interest)})",
                    }
                ),
                Command.create(
                    {
                        "account_id": self.expense_account_id.id,
                        "debit": line.interest,
                        "name": self._get_move_label(line, self.env._("Interest")),
                    }
                ),
            ],
        }

    def _prepare_reclassification_move_vals(
        self, line, short_term_lines, reverse
    ) -> dict:
        self.check_singleton()
        amount = sum(short_term_lines.mapped("principal"))
        from_date = format_date(self.env, short_term_lines[0].date, date_format="MM/y")
        to_date = format_date(self.env, short_term_lines[-1].date, date_format="MM/y")
        kind = (
            self.env._("Reversal reclassification LT - ST")
            if reverse
            else self.env._("Reclassification LT - ST")
        )
        window = f"{kind} {from_date} to {to_date}"
        long_term_side = "credit" if reverse else "debit"
        short_term_side = "debit" if reverse else "credit"
        move_date = line.date + relativedelta(day=31)
        if reverse:
            move_date += relativedelta(days=1)
        return {
            "company_id": self.company_id.id,
            "auto_post": "at_date",
            "generating_loan_line_id": line.id,
            "is_loan_payment_move": False,
            "journal_id": self.journal_id.id,
            "date": move_date,
            "ref": f"{self.name} - {window}",
            "line_ids": [
                Command.create(
                    {
                        "account_id": self.long_term_account_id.id,
                        long_term_side: amount,
                        "name": f"{self.name} - {window} (To {self.short_term_account_id.code})",
                    }
                ),
                Command.create(
                    {
                        "account_id": self.short_term_account_id.id,
                        short_term_side: amount,
                        "name": f"{self.name} - {window} (From {self.long_term_account_id.code})",
                    }
                ),
            ],
        }

    def _check_confirmable(self) -> None:
        for loan in self:
            if loan.state != "draft":
                raise UserError(
                    self.env._(
                        "%s is already confirmed. Reset it to draft before confirming it again.",
                        loan.display_name,
                    )
                )
            if not loan.name:
                raise UserError(self.env._("The loan name should be set."))
            if loan.is_wrong_date:
                raise UserError(
                    self.env._(
                        "The loan date should be earlier than the loan lines date."
                    )
                )
            rounding = loan.currency_id.rounding
            if float_compare(
                loan.amount_borrowed_difference, 0.0, precision_rounding=rounding
            ):
                raise UserError(
                    self.env._(
                        "The loan amount %(loan_amount)s should be equal to the sum of the principals: %(principal_sum)s (difference %(principal_difference)s)",
                        loan_amount=loan.currency_id.format(loan.amount_borrowed),
                        principal_sum=loan.currency_id.format(
                            sum(loan.line_ids.mapped("principal"))
                        ),
                        principal_difference=loan.currency_id.format(
                            loan.amount_borrowed_difference
                        ),
                    )
                )
            if float_compare(
                loan.interest_difference, 0.0, precision_rounding=rounding
            ):
                raise UserError(
                    self.env._(
                        "The loan interest %(loan_interest)s should be equal to the sum of the loan lines interest: %(interest_sum)s",
                        loan_interest=loan.currency_id.format(loan.interest),
                        interest_sum=loan.currency_id.format(
                            sum(loan.line_ids.mapped("interest"))
                        ),
                    )
                )
            if loan.duration_difference != 0:
                raise UserError(
                    self.env._(
                        "The loan duration should be equal to the number of loan lines."
                    )
                )
            if (
                not loan.long_term_account_id
                or not loan.short_term_account_id
                or not loan.expense_account_id
            ):
                raise UserError(self.env._("The loan accounts should be set."))
            if not loan.journal_id:
                raise UserError(self.env._("The loan journal should be set."))

    def action_confirm(self):
        self._check_confirmable()

        payment_values = []
        reclassification_values = []
        reversal_values = []
        for loan in self:
            for line, short_term_lines in loan._iter_schedule_windows():
                if loan._is_skipped(line):
                    continue
                payment_values.append(loan._prepare_payment_move_vals(line))
                if not short_term_lines:
                    continue
                reclassification_values.append(
                    loan._prepare_reclassification_move_vals(
                        line, short_term_lines, reverse=False
                    )
                )
                reversal_values.append(
                    loan._prepare_reclassification_move_vals(
                        line, short_term_lines, reverse=True
                    )
                )

        moves = self.env["account.move"]
        payments = moves.create(payment_values)
        reclassifications = moves.create(reclassification_values)
        reversals = moves.create(reversal_values)

        self._link_reversals(reclassifications, reversals)
        due = (payments | reclassifications | reversals).filtered(
            lambda move: move.date <= fields.Date.context_today(self)
        )
        due.action_post()
        self._settle_state()

    def _link_reversals(self, reclassifications, reversals) -> None:
        bodies = {}
        for reclassification, reversal in zip(
            reclassifications, reversals, strict=True
        ):
            reversal.reversed_entry_id = reclassification
            bodies[reclassification.id] = self.env._(
                "This entry has been %s",
                reversal._get_html_link(title=self.env._("reversed")),
            )
        reclassifications._message_log_batch(bodies=bodies)
        reversal_bodies = {
            reversal.id: self.env._(
                "This entry has been reversed from %s",
                reclassification._get_html_link(),
            )
            for reclassification, reversal in zip(
                reclassifications, reversals, strict=True
            )
        }
        reversals._message_log_batch(bodies=reversal_bodies)

    def action_upload_amortization_schedule(self, attachment_id) -> dict:
        attachment = self.env["ir.attachment"].browse(attachment_id)
        if attachment.mimetype not in IMPORTABLE_MIMETYPES:
            raise UserError(
                self.env._(
                    "%(filename)s cannot be imported. Supported formats: %(formats)s.",
                    filename=attachment.name,
                    formats=IMPORTABLE_EXTENSIONS,
                )
            )
        loan = self or self.create({"name": attachment.name})
        loan._clear_schedule()
        loan.message_post(
            body=self.env._("Uploaded file"), attachment_ids=[attachment.id]
        )
        import_wizard = self.env["base_import.import"].create(
            {
                "res_model": "account.loan.line",
                "file": attachment.raw,
                "file_name": attachment.name,
                "file_type": attachment.mimetype,
            }
        )
        return {
            "type": "ir.actions.client",
            "tag": "import_loan",
            "params": {
                "model": "account.loan.line",
                "context": {
                    **self.env.context,
                    "wizard_id": import_wizard.id,
                    "default_loan_id": loan.id,
                },
                "filename": attachment.name,
            },
        }

    def action_file_uploaded(self):
        self.check_singleton()
        if not self.line_ids:
            return self._get_loan_action(
                self.env._("Loans"), views=[(False, "list"), (False, "form")]
            )
        self._sync_header_with_schedule()
        return self._get_loan_action(self.env._("Loans"), res_id=self.id)

    def _sync_header_with_schedule(self) -> None:
        for loan in self:
            schedule = loan._get_ordered_lines()
            loan.amount_borrowed = sum(schedule.mapped("principal"))
            loan.interest = sum(schedule.mapped("interest"))
            loan.duration = len(schedule)
            loan.date = schedule[0].date if schedule else False

    def _clear_schedule(self) -> None:
        for loan in self:
            if loan.state != "draft":
                raise UserError(
                    self.env._(
                        "Reset %s to draft before replacing its amortization schedule.",
                        loan.display_name,
                    )
                )
        self.line_ids.generated_move_ids._unlink_or_reverse()
        self.line_ids.unlink()

    def _get_loan_action(self, name, res_id=None, views=None):
        action = {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": self._name,
            "views": views or [(False, "form")],
            "target": "self",
            "context": self.env.context,
        }
        if res_id:
            action["res_id"] = res_id
        return action

    def _create_wizard_action(self, name, model, values) -> dict[str, Any]:
        wizard = self.env[model].create(values)
        return {
            "name": name,
            "type": "ir.actions.act_window",
            "res_model": model,
            "res_id": wizard.id,
            "views": [(False, "form")],
            "target": "new",
        }

    def action_view_compute_wizard(self):
        if not self:
            raise UserError(self.env._("Please add a name before computing the loan"))
        self.check_singleton()
        values = {"loan_id": self.id, "loan_amount": self.amount_borrowed}
        if self.date:
            values["start_date"] = self.date
            values["first_payment_date"] = self.date.replace(day=1) + relativedelta(
                months=1
            )
        return self._create_wizard_action(
            self.env._("Compute New Loan"),
            "wizard.account.loan.create.schedule",
            values,
        )

    def action_reset(self):
        self.check_singleton()
        self._clear_schedule()

    def action_close(self):
        self.check_singleton()
        return self._create_wizard_action(
            self.env._("Close"), "wizard.account.loan.close", {"loan_id": self.id}
        )

    def _reset_generated_entries(self) -> None:
        self.line_ids.generated_move_ids.filtered(
            lambda move: move.state != "cancel"
        )._unlink_or_reverse()

    def action_cancel(self):
        self._reset_generated_entries()
        self._set_state("cancelled")

    def action_set_to_draft(self):
        self._reset_generated_entries()
        self._set_state("draft")

    def action_view_loan_entries(self):
        self.check_singleton()
        action = records_action(
            self.env._("Loan Entries"), self.line_ids.generated_move_ids
        )
        action["views"] = [
            (
                self.env.ref(
                    "account_loans.account_loan_view_account_move_list_view"
                ).id,
                "list",
            ),
            (False, "form"),
        ]
        return action

    def action_view_linked_assets(self):
        self.check_singleton()
        return records_action(self.env._("Linked Assets"), self.linked_assets_ids)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_posted_entries(self) -> None:
        for loan in self:
            if loan.state in ("running", "closed"):
                raise UserError(
                    self.env._(
                        "You cannot delete %(loan)s while it is %(state)s. Reset it to draft first.",
                        loan=loan.display_name,
                        state=dict(
                            self._fields["state"]._description_selection(self.env)
                        ).get(loan.state),
                    )
                )
            if loan.line_ids.generated_move_ids.filtered(
                lambda move: move.state == "posted"
            ):
                raise UserError(
                    self.env._(
                        "You cannot delete %s: it is linked to posted journal entries.",
                        loan.display_name,
                    )
                )
            loan._reset_generated_entries()
