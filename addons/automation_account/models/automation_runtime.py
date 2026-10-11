from typing import Any

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.fields import Domain

from odoo.addons.automation.models.workflow_edge import SETTLED_STATES


class AutomationRuntime(models.Model):
    _inherit = "automation.runtime"

    partner_id = fields.Many2one(
        help="The partner the operation is about: the customer whose debt a "
        "collection reduces, whoever a document is made out to.",
    )
    third_party_id = fields.Many2one(
        help="The party a fiscal document is made out to when it is not the "
        "partner, such as the generic public for a customer who takes no "
        "invoice. Leave it empty when the partner is invoiced himself.",
    )
    company_ids = fields.Many2many(
        help="Every company this run creates documents in; the run is listed "
        "in each of them. With two, the one that owns the bank statement "
        "line is the vehicle that received the money and the other holds "
        "the transaction with the partner.",
    )
    st_line_id = fields.Many2one(
        comodel_name="account.bank.statement.line",
        string="Bank Statement Line",
        index="btree_not_null",
        ondelete="set null",
        help="Related bank statement line (for bank reconciliation workflows)",
    )
    problem_message = fields.Text(
        string="What Would Stop This Run",
        compute="_compute_problem_message",
        help="What the steps still to run are missing, read from the steps "
        "that declare what they do.",
    )

    @api.constrains("st_line_id", "automation_id", "state")
    def _check_one_run_per_statement_line(self) -> None:
        runs = self.filtered(lambda run: run.st_line_id and run.state != "cancel")
        if not runs:
            return
        started = self.search(
            [
                ("st_line_id", "in", runs.st_line_id.ids),
                ("state", "!=", "cancel"),
            ],
        )
        started_by_key = started.grouped(
            lambda other: (other.st_line_id, other.automation_id),
        )
        for run in runs:
            clash = started_by_key[run.st_line_id, run.automation_id] - run
            if clash:
                raise ValidationError(
                    self.env._(
                        "%(line)s already started '%(workflow)s' as %(run)s. A "
                        "bank statement line starts each workflow once; cancel "
                        "%(run)s to start it again.",
                        line=run.st_line_id.display_name,
                        workflow=run.automation_id.name,
                        run=clash[:1].name,
                    ),
                )

    def _is_intercompany(self) -> bool:
        self.check_singleton()
        return len(self.company_ids) > 1

    def _get_vehicle_company(self) -> models.Model:
        self.check_singleton()
        st_line = self.st_line_id.with_context(
            allowed_company_ids=list(self.env.user._get_company_ids()),
        )
        return (st_line.company_id or self.company_ids[:1])._origin

    def _get_transaction_company(self) -> models.Model:
        self.check_singleton()
        vehicle = self._get_vehicle_company()
        return (self.company_ids._origin - vehicle)[:1] or vehicle

    def _execution_company_ids(self) -> list[int]:
        self.check_singleton()
        companies = self.company_ids._origin
        if not self.env.su:
            granted = list(self.env.user._get_company_ids())
            if any(company.id not in granted for company in companies) or (
                self.ids
                and self.search_count(
                    Domain("id", "=", self.id)
                    & Domain("company_ids", "any!", Domain("id", "not in", granted)),
                    limit=1,
                )
            ):
                raise UserError(
                    self.env._(
                        "Workflow %(run)s works in a company your user does "
                        "not belong to. Ask an administrator to give you "
                        "every company of the run.",
                        run=self.name,
                    ),
                )
        companies = self._get_vehicle_company() | companies
        return list(dict.fromkeys([*companies.ids, *self.env.companies.ids]))

    def _get_problem_triggers(self) -> list[str]:
        return [
            "automation_id",
            "partner_id",
            "third_party_id",
            "company_ids",
            "amount",
            "st_line_id",
            "line_ids.state",
        ]

    @api.depends(lambda self: self._get_problem_triggers())
    def _compute_problem_message(self) -> None:
        for runtime in self:
            try:
                problems = runtime._get_workflow_problems()
            except AccessError:
                problems = []
            runtime.problem_message = "\n".join(problems)

    def _get_pending_steps(self) -> models.Model:
        self.check_singleton()
        if self.state in ("done", "cancel"):
            return self.env["ir.actions.server"]
        if self.line_ids:
            lines = self.line_ids.filtered(
                lambda line: (
                    line.state not in SETTLED_STATES
                    or (line.state == "error" and not line._contains_its_error())
                ),
            )
            return lines.sorted("sequence").action_id
        return self.automation_id.action_server_ids.sorted("sequence")

    def _get_workflow_problems(self) -> list[str]:
        self.check_singleton()
        if not self._get_pending_steps():
            return []
        if self._is_intercompany():
            try:
                self = self.with_context(
                    allowed_company_ids=self._execution_company_ids(),
                )
            except UserError as error:
                return [str(error)]
        steps = self._get_pending_steps()
        problems = []
        if steps and len(self.company_ids) > 2:
            problems.append(
                self.env._(
                    "This run names %(count)s companies. A step tells the "
                    "company that received the money from the one that holds "
                    "the transaction, so a run works in two at most.",
                    count=len(self.company_ids),
                ),
            )
        elif steps and self._is_intercompany() and not self.st_line_id:
            problems.append(
                self.env._(
                    "This run names two companies and no bank statement line, "
                    "so nothing says which of them received the money.",
                ),
            )
        elif (
            self.st_line_id
            and self._get_vehicle_company() not in self.company_ids._origin
        ):
            problems.append(
                self.env._(
                    "The bank statement line belongs to %(company)s, which is "
                    "not one of this run's companies.",
                    company=self._get_vehicle_company().name,
                ),
            )
        return problems + [
            problem for step in steps for problem in step._get_workflow_problems(self)
        ]

    def _prepare_execution_context(self) -> dict[str, Any]:
        ctx = super()._prepare_execution_context()
        ctx.update(
            {
                "st_line_id": self.st_line_id.id,
                "third_party_id": self.third_party_id.id,
            },
        )
        return ctx

    def action_start(self):
        result = super().action_start()
        self._run_start_steps()
        return result

    def _run_start_steps(self) -> None:
        for runtime in self.filtered(
            lambda run: (
                run.state == "in_progress"
                and run.st_line_id
                and not run.automation_id.is_paused
            ),
        ):
            context = runtime._prepare_execution_context()
            for line in runtime.line_ids.filtered(
                lambda line: line.state == "ready" and line.action_id.run_at_start,
            ):
                line.with_context(
                    **context,
                    runtime_id=runtime.id,
                    runtime_line_id=line.id,
                ).action_execute()
