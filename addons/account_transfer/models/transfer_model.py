import ast
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models
from odoo.api import ValuesType
from odoo.exceptions import UserError, ValidationError
from odoo.fields import Domain
from odoo.libs.numbers import float_compare, float_is_zero, float_round
from odoo.tools import frozendict, groupby
from odoo.tools.date_utils import time_unit_selection


class AccountTransferModel(models.Model):
    _name = "account.transfer.model"
    _inherit = ["mixin.recurrence.interval"]
    _description = "Account Transfer Model"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("company_id", shared=False),
        }
    )

    def _default_date_start(self):
        company = self.env.company
        return (
            company.compute_fiscalyear_dates(date.today())["date_from"]
            if company
            else None
        )

    def _get_default_journal(self):
        return self.env["account.journal"].search(
            [
                *self.env["account.journal"]._check_company_domain(self.env.company),
                ("type", "=", "general"),
            ],
            limit=1,
        )

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    journal_id = fields.Many2one(
        comodel_name="account.journal",
        string="Destination Journal",
        default=lambda self: self._get_default_journal(),
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="journal_id.company_id",
        readonly=True,
    )
    date_start = fields.Date(
        string="Start Date",
        default=lambda self: self._default_date_start(),
        required=True,
    )
    date_stop = fields.Date(
        string="Stop Date",
        required=False,
    )
    repeat_unit = fields.Selection(
        selection=time_unit_selection("month", "year"),
        default="month",
    )
    account_ids = fields.Many2many(
        comodel_name="account.account",
        relation="account_model_rel",
        string="Origin Accounts",
        domain="[('account_type', '!=', 'off_balance')]",
    )
    line_ids = fields.One2many(
        comodel_name="account.transfer.model.line",
        inverse_name="transfer_model_id",
        string="Destination Accounts",
    )
    move_ids = fields.One2many(
        comodel_name="account.move",
        inverse_name="transfer_model_id",
        string="Generated Moves",
    )
    move_ids_count = fields.Count(count_of="move_ids")
    has_draft_moves = fields.Boolean(compute="_compute_has_draft_moves")
    total_percent = fields.Float(
        compute="_compute_total_percent",
        readonly=True,
    )
    state = fields.Selection(
        selection=[("disabled", "Disabled"), ("in_progress", "In Progress")],
        default="disabled",
        required=True,
    )
    conditions = fields.Char(
        default="[]",
        help="A domain to filter the accounts from which the resulting entry will transfer amounts.",
    )

    def copy(self, default=None):
        new_models = super().copy(default)
        for old_model, new_model in zip(self, new_models, strict=True):
            new_model.account_ids += old_model.account_ids
            old_model.line_ids.copy({"transfer_model_id": new_model.id})
        return new_models

    @api.ondelete(at_uninstall=False)
    def _unlink_with_check_moves(self) -> None:
        for transfer in self:
            if transfer.move_ids_count > 0:
                posted_moves = any(move.state == "posted" for move in transfer.move_ids)
                if posted_moves:
                    raise UserError(
                        self.env._(
                            "You cannot delete a transfer model that has posted moves attached ('%s').",
                            transfer.name,
                        )
                    )
                draft_moves = any(move.state == "draft" for move in transfer.move_ids)
                if draft_moves:
                    raise UserError(
                        self.env._(
                            "You cannot delete a transfer model that has draft moves attached ('%s'). "
                            "Please delete them before deleting this transfer.",
                            transfer.name,
                        )
                    )

    @api.depends("move_ids")
    def _compute_has_draft_moves(self) -> None:
        for record in self:
            record.has_draft_moves = any(
                move.state == "draft" for move in record.move_ids
            )

    @api.constrains("line_ids")
    def _check_line_ids_percent(self) -> None:
        for record in self:
            if not 0 < record.total_percent <= 100.0:
                raise ValidationError(
                    self.env._(
                        "The total percentage (%s) should be less or equal to 100!",
                        record.total_percent,
                    )
                )

    @api.depends("line_ids")
    def _compute_total_percent(self) -> None:
        for record in self:
            total_percent = sum(
                record.line_ids.filtered(lambda line: line.account_id).mapped("percent")
            )
            record.total_percent = float_round(total_percent, precision_digits=6)

    def action_enable(self):
        return self.write({"state": "in_progress"})

    def action_disable(self):
        return self.write({"state": "disabled"})

    def action_archive(self):
        self.action_disable()
        return super().action_archive()

    @api.model
    def action_cron_auto_transfer(self) -> None:
        self.search([("state", "=", "in_progress")]).action_perform_auto_transfer()

    def action_perform_auto_transfer(self) -> None:
        for record in self:
            if record.account_ids and record.line_ids:
                today = date.today()
                max_date = (record.date_stop and min(today, record.date_stop)) or today
                start_date = record._get_start_date()
                next_move_date = record._get_next_move_date(start_date)

                while next_move_date <= max_date:
                    record._create_or_update_move_for_period(start_date, next_move_date)
                    start_date = next_move_date + relativedelta(days=1)
                    next_move_date = record._get_next_move_date(start_date)

                if not record.date_stop:
                    record._create_or_update_move_for_period(start_date, next_move_date)
                elif today < record.date_stop:
                    record._create_or_update_move_for_period(
                        start_date, min(next_move_date, record.date_stop)
                    )

    def _create_or_update_move_for_period(self, start_date, end_date):
        self.check_singleton()
        current_move = self._get_move_for_period(end_date)
        if current_move and current_move.state != "draft":
            return current_move
        line_values = self._prepare_transfer_move_line_vals_list(start_date, end_date)
        if line_values:
            if current_move is None:
                current_move = self.env["account.move"].create(
                    {
                        "ref": "%s: %s --> %s"
                        % (self.name, str(start_date), str(end_date)),
                        "date": end_date,
                        "journal_id": self.journal_id.id,
                        "transfer_model_id": self.id,
                    }
                )

            line_ids_values = [Command.create(value) for value in line_values]
            current_move.line_ids.unlink()
            current_move.write({"line_ids": line_ids_values})
        return current_move

    def _get_move_for_period(self, end_date):
        self.check_singleton()
        domain = Domain("date", "=", end_date) & Domain(
            "transfer_model_id", "=", self.id
        )
        current_moves = self.env["account.move"].search(
            domain, limit=1, order="date desc"
        )
        return current_moves[0] if current_moves else None

    def _get_start_date(self):
        self.check_singleton()
        global_lock_date = (
            self.company_id.account_config_id.fiscalyear_lock_date
            or fields.Date.to_date("1900-01-01")
        )
        hard_lock_date = (
            self.company_id.account_config_id.hard_lock_date
            or fields.Date.to_date("1900-01-01")
        )
        return max(
            global_lock_date.replace(day=1),
            hard_lock_date.replace(day=1),
            self.date_start,
        )

    def _get_next_move_date(self, date):
        self.check_singleton()
        return date + self._get_recurrence_delta() - relativedelta(days=1)

    def _prepare_transfer_move_line_vals_list(
        self, start_date, end_date
    ) -> list[ValuesType]:
        self.check_singleton()

        transferred_amls = self.env["account.move.line"].search(
            [
                ("account_id", "in", self.account_ids.ids),
                ("date", ">=", start_date),
                ("date", "<=", end_date),
                ("parent_state", "=", "posted"),
                *ast.literal_eval(self.conditions),
            ]
        )

        if not transferred_amls:
            return []

        values = []
        currency_round = self.company_id.currency_id.round
        transfer_lines_total_percentage_is_hundred = (
            float_compare(sum(self.mapped("line_ids.percent")), 100, precision_digits=6)
            == 0
        )
        transferred_lines_by_account = dict(
            groupby(transferred_amls, lambda aml: aml.account_id.id)
        )
        transferred_lines_total_balance = sum(transferred_amls.mapped("balance"))
        amount_to_transfer = 0

        for source_account in self.account_ids:
            transferred_lines_balance = sum(
                transferred_line.balance
                for transferred_line in transferred_lines_by_account.get(
                    source_account.id, []
                )
            )
            if not float_is_zero(transferred_lines_balance, precision_digits=6):
                percentage = sum(self.line_ids.mapped("percent"))
                amount = currency_round(
                    transferred_lines_balance * (percentage / 100.0)
                )
                values.append(
                    {
                        "name": self.env._(
                            "Transfer (%(percent)s%% from %(account)s)",
                            percent=percentage,
                            account=source_account.name,
                        ),
                        "account_id": source_account.id,
                        "balance": -amount,
                        "date_maturity": end_date,
                    }
                )
                amount_to_transfer += amount

        for transfer_line in self.line_ids:
            destination_account = transfer_line.account_id
            if (
                transfer_lines_total_percentage_is_hundred
                and destination_account == self.line_ids.mapped("account_id")[-1]
            ):
                amount = amount_to_transfer
            else:
                amount = transferred_lines_total_balance * (
                    transfer_line.percent / 100.0
                )
            amount = currency_round(amount)
            if not float_is_zero(amount, precision_digits=6):
                values.append(
                    {
                        "name": self.env._(
                            "Transfer (-%(percent)s%% to %(account)s)",
                            percent=transfer_line.percent,
                            account=destination_account.name,
                        ),
                        "account_id": destination_account.id,
                        "balance": amount,
                        "date_maturity": end_date,
                    }
                )
                amount_to_transfer -= amount

        return values
