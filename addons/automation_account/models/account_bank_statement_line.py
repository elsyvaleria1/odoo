from odoo import api, fields, models
from odoo.fields import Domain


class AccountBankStatementLine(models.Model):
    _inherit = "account.bank.statement.line"

    automation_runtime_ids = fields.One2many(
        comodel_name="automation.runtime",
        inverse_name="st_line_id",
        string="Automation Workflows",
    )
    automation_runtime_id = fields.Many2one(
        comodel_name="automation.runtime",
        string="Automation Workflow",
        compute="_compute_automation_runtime_id",
        help="Latest workflow started from this line, ignoring cancelled ones.",
    )
    # Computed beside the run rather than related through it: a related field
    # is refreshed by searching the many2one it goes through, and that one has
    # no column, so a run changing state with a line's state in cache raised
    # "Cannot convert ... to SQL because it is not stored".
    automation_runtime_state = fields.Selection(
        selection="_selection_runtime_states",
        string="Automation Workflow State",
        compute="_compute_automation_runtime_id",
    )

    @api.model
    def _selection_runtime_states(self) -> list[tuple[str, str]]:
        state = self.env["automation.runtime"]._fields["state"]
        return state._description_selection(self.env)

    @api.depends("automation_runtime_ids.state")
    def _compute_automation_runtime_id(self) -> None:
        for line in self:
            runs = line.automation_runtime_ids.filtered(
                lambda run: run.state != "cancel",
            )
            latest = runs.sorted("id")[-1:]
            line.automation_runtime_id = latest
            line.automation_runtime_state = latest.state

    def _get_domain_settled_elsewhere(self) -> Domain:
        # a transaction a live workflow was started from is settled by that
        # workflow's own steps
        return super()._get_domain_settled_elsewhere() | Domain(
            "automation_runtime_ids",
            "any",
            [("state", "in", ("draft", "in_progress", "waiting_resume"))],
        )
