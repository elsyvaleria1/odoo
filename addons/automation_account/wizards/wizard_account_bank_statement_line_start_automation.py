from typing import Any

from markupsafe import Markup

from odoo import api, fields, models
from odoo.fields import Command, Date


class WizardAccountBankStatementLineStartAutomation(models.TransientModel):
    _name = "wizard.account.bank.statement.line.start.automation"
    _description = "Create Automation Runtime from Bank Statement"

    st_line_id = fields.Many2one(
        comodel_name="account.bank.statement.line",
        string="Bank Statement Line",
        readonly=True,
        help="Source bank statement line that triggered this workflow",
    )
    automation_id = fields.Many2one(
        comodel_name="automation.rule",
        string="Automation Workflow",
        required=True,
        domain="[('model_id.model', '=', 'automation.runtime.line'), "
        "('trigger', '=', 'on_hand'), ('id', 'not in', started_automation_ids)]",
        help="Select the automation workflow to execute",
    )
    started_automation_ids = fields.Many2many(
        comodel_name="automation.rule",
        compute="_compute_started_automation_ids",
        help="The workflows this bank statement line has already started and "
        "not cancelled, which it cannot start again",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        required=True,
        domain=["|", ("parent_id", "=", False), ("is_company", "=", True)],
    )
    third_party_id = fields.Many2one(
        comodel_name="res.partner",
        domain=["|", ("parent_id", "=", False), ("is_company", "=", True)],
        help="The party a fiscal document is made out to when it is not the "
        "partner, such as the generic public for a customer who takes no "
        "invoice. Leave it empty when the partner is invoiced himself.",
    )
    reference = fields.Char(help="Reference or description for this operation")
    amount = fields.Monetary(
        currency_field="currency_id",
        required=True,
        help="Absolute amount of the operation. A statement line's sign is "
        "dropped on purpose: direction is carried by the workflow and the "
        "templates it runs, which are direction-specific, not by this "
        "number. Nothing downstream recovers the sign, so do not read one "
        "into it.",
    )
    date = fields.Date(
        default=fields.Date.context_today,
        required=True,
    )
    company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="wizard_st_line_start_automation_company_rel",
        column1="wizard_id",
        column2="company_id",
        string="Companies",
        default=lambda self: self.env.company,
        required=True,
        help="Every company the run creates documents in. It starts with the "
        "company of the bank statement line; add the company that holds "
        "the transaction with the partner when another one's bank received "
        "the money.",
    )
    currency_id = fields.Many2one(
        comodel_name="res.currency",
        default=lambda self: self.env.company.currency_id,
        required=True,
    )
    plan_preview = fields.Html(
        string="What This Run Does",
        compute="_compute_plan",
        help="What each step of the workflow does with the values above, for "
        "the steps that declare it.",
    )
    problem_message = fields.Text(
        string="What Would Stop This Run",
        compute="_compute_plan",
    )

    @api.depends("st_line_id")
    def _compute_started_automation_ids(self) -> None:
        for wizard in self:
            wizard.started_automation_ids = (
                wizard.st_line_id.automation_runtime_ids.filtered(
                    lambda run: run.state != "cancel",
                ).automation_id
            )

    def _get_plan_triggers(self) -> list[str]:
        return [
            "automation_id",
            "partner_id",
            "third_party_id",
            "company_ids",
            "amount",
            "st_line_id",
        ]

    @api.depends(lambda self: self._get_plan_triggers())
    def _compute_plan(self) -> None:
        Runtime = self.env["automation.runtime"].with_context(
            allowed_company_ids=list(self.env.user._get_company_ids()),
        )
        for wizard in self:
            runtime = Runtime.new(wizard._prepare_runtime_vals())
            steps = runtime._get_pending_steps()
            rows = [
                (step.name, step._get_workflow_step_summary(runtime)) for step in steps
            ]
            wizard.plan_preview = (
                Markup("<ol class='mb-0'>%s</ol>")
                % Markup().join(
                    Markup("<li><strong>%s</strong>%s</li>")
                    % (name, Markup(": %s") % summary if summary else "")
                    for name, summary in rows
                )
                if rows
                else False
            )
            wizard.problem_message = "\n".join(runtime._get_workflow_problems())

    @api.model
    def default_get(self, fields) -> dict[str, Any]:
        res = super().default_get(fields)
        ctx = self.env.context

        st_line = self.env["account.bank.statement.line"]
        if ctx.get("active_model") == "account.bank.statement.line" and ctx.get(
            "active_id",
        ):
            st_line = st_line.browse(ctx["active_id"]).exists()

        if st_line:
            res.update(
                {
                    "st_line_id": st_line.id,
                    "reference": st_line.payment_ref or st_line.ref,
                    "amount": abs(st_line.amount),
                    "currency_id": (
                        st_line.currency_id.id
                        or st_line.journal_id.currency_id.id
                        or self.env.company.currency_id.id
                    ),
                    "date": st_line.date or Date.context_today(self),
                    "company_ids": [Command.set(st_line.company_id.ids)],
                },
            )
            customer = res.get("partner_id")
            if not customer:
                res["partner_id"] = st_line.partner_id.id
            elif st_line.partner_id and st_line.partner_id.id != customer:
                res.setdefault("third_party_id", st_line.partner_id.id)

        return res

    def _link_approval_request(self, runtime) -> None:
        pass

    def _prepare_runtime_vals(self) -> dict[str, Any]:
        self.check_singleton()
        runtime_vals = {
            "automation_id": self.automation_id.id,
            "partner_id": self.partner_id.id,
            "reference": self.reference,
            "amount": self.amount,
            "currency_id": self.currency_id.id,
            "date": self.date,
            "company_ids": [Command.set(self.company_ids.ids)],
            "st_line_id": self.st_line_id.id,
        }

        if self.third_party_id:
            runtime_vals["third_party_id"] = self.third_party_id.id

        return runtime_vals

    def action_create_runtime(self) -> dict[str, Any]:
        self.check_singleton()

        runtime = self.env["automation.runtime"].create(self._prepare_runtime_vals())
        self._link_approval_request(runtime)

        runtime.action_start()

        return {
            "name": self.env._("Automation Workflow"),
            "type": "ir.actions.act_window",
            "res_model": "automation.runtime",
            "view_mode": "form",
            "target": "current",
            "res_id": runtime.id,
            "context": {"create": False},
        }
