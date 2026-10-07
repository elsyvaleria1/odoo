from datetime import datetime, time

from odoo import api, fields, models

AUTOFIX_KINDS = ("error_incident.diagnose", "error_incident.fix")
REVISION = "error_incident.revision"
HOTFIX = "error_incident.hotfix"
# Runs of the deploy runner on the production host: no agent, no model key.
DELIVERY_KINDS = (REVISION, HOTFIX)


class ErrorIncidentAutofixPolicy(models.Model):
    """When an incident is handed to the agents, and what they may do with it.
    One active policy; its company pays."""

    _name = "error.incident.autofix.policy"
    _description = "Autofix Policy"
    _inherit = ["mixin.mail.thread"]

    name = fields.Char(
        required=True,
    )
    active = fields.Boolean(
        default=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        required=True,
        help="Whose machine-learning budget the runs count against.",
    )
    mode = fields.Selection(
        selection=[
            ("off", "Off"),
            ("shadow", "Shadow"),
            ("live", "Live"),
        ],
        default="off",
        required=True,
        tracking=True,
        help="Off: nothing is dispatched. Shadow: incidents are diagnosed and "
        "fixes proposed for review, nothing is pushed and users see nothing. "
        "Live: the runner pushes the fix and opens its pull request.",
    )
    min_occurrences = fields.Integer(
        default=2,
        help="An incident is dispatched once it occurred this often.",
    )
    require_internal_user = fields.Boolean(
        default=True,
        help="Only an incident an internal user hit; a scheduled action or a "
        "job failing alone waits for a person.",
    )
    pass_without_checks = fields.Boolean(
        string="Pass Without Checks",
        help="A fix's pull request that no check runs on -- a repository without "
        "CI -- counts as passing, so it can be merged or hotfixed once a person "
        "approves it. Off, such a fix waits in Testing.",
    )
    excluded_exception_types = fields.Text(
        default="odoo.exceptions.AccessError\nodoo.exceptions.AccessDenied",
        help="One exception per line, as a traceback prints it: granting access "
        "is a person's decision.",
    )
    excluded_modules = fields.Text(
        help="One module per line, never handed to the agents.",
    )
    daily_run_cap = fields.Integer(
        default=10,
        help="Agent runs queued per day at most, diagnoses and fixes together.",
    )
    max_attempts = fields.Integer(
        default=3,
        help="Fix attempts per incident before it waits for a person; a "
        "regression starts the count again.",
    )
    diagnose_model = fields.Char(
        default="claude-fable-5-1",
    )
    fix_model = fields.Char(
        default="claude-opus-5-5",
    )
    diagnose_timeout = fields.Integer(
        string="Diagnosis Timeout (s)",
        default=1800,
    )
    fix_timeout = fields.Integer(
        string="Fix Timeout (s)",
        default=3600,
    )
    commit_author_name = fields.Char(
        default="AgroMarin Autofix",
    )
    commit_author_email = fields.Char(
        default="autofix@agromarin.mx",
    )

    _min_occurrences_positive = models.Constraint(
        "CHECK(min_occurrences > 0)",
        "An incident occurs at least once.",
    )

    @api.model
    def _current(self) -> ErrorIncidentAutofixPolicy:
        return self.search([], order="id", limit=1)

    def _lines(self, field_name: str) -> set[str]:
        return {
            line.strip()
            for line in (self[field_name] or "").splitlines()
            if line.strip()
        }

    def _runs_today(self) -> int:
        midnight = datetime.combine(fields.Date.context_today(self), time.min)
        return self.env["agent.run"].search_count(
            [
                ("kind", "in", AUTOFIX_KINDS),
                ("company_id", "=", self.company_id.id),
                ("create_date", ">=", midnight),
            ]
        )

    def _under_daily_cap(self) -> bool:
        return self._runs_today() < self.daily_run_cap
