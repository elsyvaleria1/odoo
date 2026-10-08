from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)


class ProjectGate(models.Model):
    _name = "project.gate"
    _access_anchors = frozendict({"company": "project_id.company_id"})
    _description = "Project Gate Review"
    _order = "sequence, id"
    _inherit = ["mixin.mail.thread"]

    name = fields.Char(
        string="Gate Name",
        required=True,
        tracking=True,
    )
    project_id = fields.Many2one(
        comodel_name="project.project",
        index=True,
        required=True,
        ondelete="cascade",
    )
    sequence = fields.Integer(
        string="Gate Order",
        default=10,
    )
    milestone_id = fields.Many2one(
        comodel_name="project.milestone",
        string="Trigger Milestone",
        domain="[('project_id', '=', project_id)]",
        help="Milestone this gate reviews: the gate can pass only once the "
        "milestone is reached.",
    )
    criterion_ids = fields.One2many(
        comodel_name="project.gate.criterion",
        inverse_name="gate_id",
        string="Review Criteria",
    )
    state = fields.Selection(
        selection=[
            ("pending", "Pending"),
            ("passed", "Passed"),
            ("failed", "Failed"),
            ("deferred", "Deferred"),
        ],
        default="pending",
        required=True,
        tracking=True,
    )
    date_review = fields.Date(
        string="Review Date",
        tracking=True,
    )
    reviewer_ids = fields.Many2many(
        comodel_name="res.users",
        string="Reviewers",
    )
    decision_notes = fields.Html()
    kill_criteria = fields.Html(
        help="Pre-defined conditions under which the project should be cancelled."
    )
    criteria_met_count = fields.Integer(
        string="Criteria Met",
        export_string_translation=False,
        compute="_compute_criteria_met_count",
    )
    criteria_total_count = fields.Count(
        count_of="criterion_ids",
        string="Total Criteria",
        export_string_translation=False,
    )

    @api.depends("criterion_ids.is_met")
    def _compute_criteria_met_count(self) -> None:
        for gate in self:
            gate.criteria_met_count = len(gate.criterion_ids.filtered("is_met"))
            _debug.logic(
                "gate_criteria_counted",
                gate=gate,
                met=gate.criteria_met_count,
                total=len(gate.criterion_ids),
                state=gate.state,
            )

    @api.constrains("state", "milestone_id")
    def _check_passed_gate_is_satisfied(self) -> None:
        for gate in self.filtered(lambda g: g.state == "passed"):
            unmet = gate.criterion_ids.filtered(lambda c: not c.is_met)
            milestone_open = gate.milestone_id and not gate.milestone_id.is_reached
            if not unmet and not milestone_open:
                continue
            _debug.logic(
                "gate_pass_refused",
                gate=gate,
                unmet=unmet,
                milestone_open=bool(milestone_open),
            )
            if unmet:
                raise ValidationError(
                    self.env._(
                        "Gate %(gate)s cannot pass while criteria are unmet: "
                        "%(criteria)s.",
                        gate=gate.name,
                        criteria=", ".join(unmet.mapped("name")),
                    )
                )
            raise ValidationError(
                self.env._(
                    "Gate %(gate)s cannot pass before its milestone %(milestone)s "
                    "is reached.",
                    gate=gate.name,
                    milestone=gate.milestone_id.display_name,
                )
            )

    def action_pass(self) -> None:
        self._update_decision("passed")

    def action_fail(self) -> None:
        self._update_decision("failed")

    def action_defer(self) -> None:
        self._update_decision("deferred")

    def action_reset(self) -> None:
        _debug.lifecycle(
            "gate_decided", gates=self, old=self.mapped("state"), new="pending"
        )
        self.state = "pending"

    def _update_decision(self, state: str) -> None:
        _debug.lifecycle(
            "gate_decided", gates=self, old=self.mapped("state"), new=state
        )
        undated = self.filtered(lambda gate: not gate.date_review)
        (self - undated).write({"state": state})
        undated.write({"state": state, "date_review": fields.Date.context_today(self)})

    @api.constrains("milestone_id", "project_id")
    def _check_milestone_project(self) -> None:
        for gate in self:
            if gate.milestone_id and gate.milestone_id.project_id != gate.project_id:
                raise ValidationError(
                    self.env._(
                        "The trigger milestone of gate %(gate)s must belong to "
                        "its project (%(project)s).",
                        gate=gate.name,
                        project=gate.project_id.display_name,
                    )
                )


class ProjectGateCriterion(models.Model):
    _name = "project.gate.criterion"
    _access_anchors = frozendict({"company": "gate_id.project_id.company_id"})
    _description = "Gate Review Criterion"
    _order = "sequence, id"

    gate_id = fields.Many2one(
        comodel_name="project.gate",
        index=True,
        required=True,
        ondelete="cascade",
    )
    name = fields.Char(
        string="Criterion",
        required=True,
    )
    sequence = fields.Integer(default=10)
    is_met = fields.Boolean(
        string="Met",
        default=False,
    )
    evidence = fields.Text()

    @api.constrains("is_met", "gate_id")
    def _check_passed_gate_keeps_criteria(self) -> None:
        self.gate_id._check_passed_gate_is_satisfied()
