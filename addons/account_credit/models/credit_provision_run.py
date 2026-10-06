from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .credit_aging import AGING_SELECTION, aging_bucket

RUN_STATES = [
    ("draft", "Draft"),
    ("computed", "Computed"),
    ("posted", "Posted"),
    ("cancel", "Cancelled"),
]


class CreditProvisionRun(models.Model):
    _name = "credit.provision.run"
    _inherit = ["mixin.mail.thread"]
    _description = "Expected Credit Loss Run"
    _order = "date desc, id desc"
    _check_company_auto = True

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    date = fields.Date(
        default=fields.Date.today,
        required=True,
        help="Receivables open on this day are aged against it.",
    )
    state = fields.Selection(
        selection=RUN_STATES,
        default="draft",
        required=True,
        tracking=True,
    )
    matrix_id = fields.Many2one(
        comodel_name="credit.provision.matrix",
        check_company=True,
    )
    line_ids = fields.One2many(
        comodel_name="credit.provision.run.line",
        inverse_name="run_id",
    )
    total_exposure = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    total_expected_loss = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_totals",
        store=True,
    )
    previous_run_id = fields.Many2one(
        comodel_name="credit.provision.run",
        readonly=True,
        help="Last posted run of the company; the entry books the difference.",
    )
    previous_expected_loss = fields.Monetary(
        related="previous_run_id.total_expected_loss",
        string="Previous Expected Loss",
        currency_field="currency_id",
    )
    amount_to_book = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_amount_to_book",
    )
    move_id = fields.Many2one(
        comodel_name="account.move",
        copy=False,
        readonly=True,
    )

    @api.depends("company_id", "date")
    def _compute_name(self):
        for run in self:
            run.name = self.env._(
                "Expected credit loss %(company)s %(date)s",
                company=run.company_id.name or "",
                date=run.date or "",
            )

    @api.depends("line_ids.amount", "line_ids.expected_loss")
    def _compute_totals(self) -> None:
        for run in self:
            run.total_exposure = sum(run.line_ids.mapped("amount"))
            run.total_expected_loss = sum(run.line_ids.mapped("expected_loss"))

    @api.depends("total_expected_loss", "previous_run_id.total_expected_loss")
    def _compute_amount_to_book(self) -> None:
        for run in self:
            run.amount_to_book = run.total_expected_loss - (
                run.previous_run_id.total_expected_loss or 0.0
            )

    @api.constrains("date", "company_id", "state")
    def _check_one_posted_per_date(self) -> None:
        for run in self.filtered(lambda r: r.state == "posted"):
            other = self.search_count(
                [
                    ("id", "!=", run.id),
                    ("company_id", "=", run.company_id.id),
                    ("date", "=", run.date),
                    ("state", "=", "posted"),
                ]
            )
            if other:
                raise ValidationError(
                    self.env._("One expected credit loss run is posted per day.")
                )

    def _matrix(self):
        self.check_singleton()
        return self.matrix_id or self.env["credit.provision.matrix"]._for_company(
            self.company_id
        )

    def _read_open_receivables(self):
        self.check_singleton()
        Profile = self.env["credit.profile"].sudo()
        profiles = Profile.search([("company_id", "=", self.company_id.id)])
        partner_ids = profiles._partner_ids_by_profile()
        profile_by_partner = {
            pid: profile for profile, ids in partner_ids.items() for pid in ids
        }
        if not profile_by_partner:
            return {}
        groups = (
            self.env["account.move.line"]
            .sudo()
            ._read_group(
                [
                    ("account_id.account_type", "=", "asset_receivable"),
                    ("parent_state", "=", "posted"),
                    ("reconciled", "=", False),
                    ("date", "<=", self.date),
                    ("company_id", "child_of", self.company_id.id),
                    ("partner_id", "in", list(profile_by_partner)),
                ],
                ["partner_id", "date_maturity:day"],
                ["amount_residual:sum"],
            )
        )
        amounts = defaultdict(lambda: defaultdict(float))
        for partner, due, residual in groups:
            profile = profile_by_partner.get(partner.id)
            if not profile or not residual or residual <= 0:
                continue
            days = (self.date - due).days if due else 0
            amounts[profile][aging_bucket(days)] += residual
        return amounts

    def action_compute(self) -> None:
        for run in self:
            if run.state == "posted":
                raise UserError(self.env._("A posted run is not recomputed."))
            matrix = run._matrix()
            if not matrix:
                raise UserError(
                    self.env._(
                        "No expected credit loss matrix is configured for %s.",
                        run.company_id.name,
                    )
                )
            commands = [Command.clear()]
            for profile, buckets in run._read_open_receivables().items():
                grade = profile.grade_effective_id or profile.grade_id
                for bucket, amount in buckets.items():
                    rate = matrix._rate_for(grade, bucket)
                    commands.append(
                        Command.create(
                            {
                                "profile_id": profile.id,
                                "grade_id": grade.id,
                                "bucket": bucket,
                                "amount": amount,
                                "rate": rate,
                                "expected_loss": amount * rate / 100.0,
                            }
                        )
                    )
            previous = self.search(
                [
                    ("company_id", "=", run.company_id.id),
                    ("state", "=", "posted"),
                    ("date", "<", run.date),
                    ("id", "!=", run.id),
                ],
                order="date desc, id desc",
                limit=1,
            )
            run.write(
                {
                    "line_ids": commands,
                    "matrix_id": matrix.id,
                    "previous_run_id": previous.id,
                    "state": "computed",
                }
            )

    def action_post(self):
        for run in self:
            if run.state != "computed":
                raise UserError(self.env._("Compute the run before posting it."))
            config = self.env["credit.config"].sudo()._for(run.company_id)
            if not (
                config.provision_journal_id
                and config.provision_expense_account_id
                and config.provision_allowance_account_id
            ):
                raise UserError(
                    self.env._(
                        "Configure the provision journal, expense account and "
                        "allowance account of %s before posting.",
                        run.company_id.name,
                    )
                )
            amount = run.currency_id.round(run.amount_to_book)
            if run.currency_id.is_zero(amount):
                run.write({"state": "posted"})
                continue
            debit_account = (
                config.provision_expense_account_id
                if amount > 0
                else config.provision_allowance_account_id
            )
            credit_account = (
                config.provision_allowance_account_id
                if amount > 0
                else config.provision_expense_account_id
            )
            move = (
                self.env["account.move"]
                .with_company(run.company_id)
                .create(
                    {
                        "move_type": "entry",
                        "journal_id": config.provision_journal_id.id,
                        "date": run.date,
                        "ref": run.name,
                        "line_ids": [
                            Command.create(
                                {
                                    "name": run.name,
                                    "account_id": debit_account.id,
                                    "debit": abs(amount),
                                    "credit": 0.0,
                                }
                            ),
                            Command.create(
                                {
                                    "name": run.name,
                                    "account_id": credit_account.id,
                                    "debit": 0.0,
                                    "credit": abs(amount),
                                }
                            ),
                        ],
                    }
                )
            )
            move.action_post()
            run.write({"move_id": move.id, "state": "posted"})

    def action_cancel(self):
        for run in self:
            if run.move_id and run.move_id.state == "posted":
                run.move_id.action_draft()
                run.move_id.action_cancel()
            run.write({"state": "cancel"})

    def action_draft(self):
        self.filtered(lambda r: r.state in ("computed", "cancel")).write(
            {"state": "draft"}
        )

    def action_view_move(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "res_model": "account.move",
            "res_id": self.move_id.id,
            "view_mode": "form",
        }


class CreditProvisionRunLine(models.Model):
    _name = "credit.provision.run.line"
    _description = "Expected Credit Loss Run Line"
    _order = "run_id, expected_loss desc, id"

    run_id = fields.Many2one(
        comodel_name="credit.provision.run",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="run_id.company_id",
        store=True,
    )
    currency_id = fields.Many2one(related="run_id.currency_id")
    profile_id = fields.Many2one(
        comodel_name="credit.profile",
        required=True,
    )
    partner_id = fields.Many2one(
        related="profile_id.partner_id",
        store=True,
    )
    grade_id = fields.Many2one(comodel_name="credit.grade")
    bucket = fields.Selection(
        selection=AGING_SELECTION,
        required=True,
    )
    amount = fields.Monetary(currency_field="currency_id")
    rate = fields.Float(digits=(5, 2))
    expected_loss = fields.Monetary(currency_field="currency_id")
