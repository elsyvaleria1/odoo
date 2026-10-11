import logging
from collections import defaultdict

from odoo import api, exceptions, fields, models
from odoo.fields import Domain
from odoo.tools.date_utils import get_timedelta, time_unit_selection
from odoo.tools.json import scriptsafe as json_scriptsafe

from ._canvas import NODE_SIZE_DEFAULT, NODE_SIZE_MAX, NODE_SIZE_MIN
from ._steps import (
    RESERVED_KEYS,
    STEP_KEY_MAX,
    References,
    collect_references,
    is_valid_step_key,
    make_step_key,
)

_logger = logging.getLogger(__name__)

STEP_REFERENCE_DEPENDS = (
    "automation_rule_id",
    "edge_in_ids",
    "edge_in_ids.source_node_id",
    "step_key",
    "step_references",
)


class IrActionsServer(models.Model):
    _inherit = "ir.actions.server"

    usage = fields.Selection(
        selection_add=[("automation", "Automation Rule")],
        ondelete={"automation": "cascade"},
    )
    automation_rule_id = fields.Many2one(
        comodel_name="automation.rule",
        index="btree_not_null",
        ondelete="cascade",
    )

    edge_in_ids = fields.One2many(
        comodel_name="workflow.edge",
        inverse_name="target_node_id",
        string="Incoming Edges",
        copy=False,
        help="Edges that must be satisfied before this action can execute",
    )
    edge_out_ids = fields.One2many(
        comodel_name="workflow.edge",
        inverse_name="source_node_id",
        string="Outgoing Edges",
        copy=False,
        help="Edges this action's outcome can satisfy",
    )

    node_type = fields.Selection(
        selection=[
            ("action", "Action"),
            ("wait", "Wait"),
            ("approval", "Approval"),
            ("input", "Input"),
            ("subflow", "Sub-workflow"),
        ],
        default="action",
        required=True,
        help="What this step does when the workflow reaches it. An Action runs "
        "the server action; a Wait pauses the run and resumes it later; an "
        "Input pauses it until someone fills in the run's fields it asks for.",
    )
    wait_delay = fields.Integer(
        string="Wait For",
        default=1,
        help="How long a Wait step pauses the run before its successors advance",
    )
    wait_unit = fields.Selection(
        selection=time_unit_selection("minute", "hour", "day"),
        default="hour",
        required=True,
    )

    start_delay = fields.Integer(
        default=0,
        help="For a step no edge leads to: how long after its run starts it "
        "becomes ready. Ignored on a step with predecessors, whose edges carry "
        "their own delays.",
    )
    start_delay_unit = fields.Selection(
        selection=time_unit_selection("minute", "hour", "day", "week", "month"),
        default="hour",
        required=True,
    )
    validity_delay = fields.Integer(
        string="Valid For",
        default=0,
        help="How long after the step becomes ready it may still run. A step "
        "reached later is skipped instead. Zero means it never expires.",
    )
    validity_unit = fields.Selection(
        selection=time_unit_selection("minute", "hour", "day", "week", "month"),
        default="hour",
        required=True,
    )

    pos_x = fields.Integer(
        string="Canvas X",
        help="Horizontal position of this node on the workflow canvas",
    )
    pos_y = fields.Integer(
        string="Canvas Y",
        help="Vertical position of this node on the workflow canvas",
    )
    pos_width = fields.Integer(
        string="Canvas Width",
        help="Width of this node on the workflow canvas; 0 means the default",
    )
    pos_height = fields.Integer(
        string="Canvas Height",
        help="Height of this node on the workflow canvas; 0 means the default",
    )

    approval_user_ids = fields.Many2many(
        comodel_name="res.users",
        relation="ir_actions_server_approval_user_rel",
        string="Approvers",
        help="Who receives an activity when an Approval step is reached. "
        "Approved By says whether everyone, or any one of them, must mark "
        "it done for the workflow to continue",
    )
    approval_mode = fields.Selection(
        selection=[("all", "Everyone"), ("any", "Anyone")],
        string="Approved By",
        default="all",
        required=True,
        help="Everyone: the step waits until each approver has marked their "
        "activity done. Anyone: the first approver to do so releases the "
        "step, and the other approvers' activities are removed",
    )
    approval_note = fields.Char(
        string="Ask For",
        help="Shown on the activity each approver receives. May read the "
        "record the run is about as object, for example "
        "{{ object.name }}, with mail's inline template syntax",
    )

    input_field_ids = fields.Many2many(
        comodel_name="ir.model.fields",
        relation="ir_actions_server_input_field_rel",
        column1="action_id",
        column2="field_id",
        string="Asks For",
        domain="[('model', '=', 'automation.runtime'), ('store', '=', True), "
        "('readonly', '=', False), ('ttype', 'not in', ('one2many', 'binary'))]",
        help="The run's fields an Input step asks someone to fill in before "
        "the workflow continues",
    )

    line_input_field_ids = fields.Many2many(
        comodel_name="ir.model.fields",
        relation="ir_actions_server_line_input_field_rel",
        column1="action_id",
        column2="field_id",
        string="Asks Before Running",
        domain="[('model', '=', 'automation.runtime.line'), ('store', '=', True), "
        "('readonly', '=', False), ('ttype', 'not in', ('one2many', 'binary'))]",
        help="Fields of this step, on each run, that must be filled before it "
        "runs. A step reached with one empty waits for someone to fill it in.",
    )

    subflow_automation_id = fields.Many2one(
        comodel_name="automation.rule",
        string="Sub-workflow",
        help="The automation a Sub-workflow step runs and waits for",
    )

    step_key = fields.Char(
        string="Key",
        help="How the code of later steps names this one: steps.<key>. "
        "Unique within the automation; derived from the name when left empty.",
    )
    input_definition = fields.PropertiesDefinition(
        string="Form",
        help="Questions this step asks before it runs. Each run keeps its own "
        "answers, which later steps read as steps.<key>.input.",
    )

    input_form_node_id = fields.Many2one(
        comodel_name="ir.actions.server",
        copy=False,
        readonly=True,
        help="The step itself: what lets its own form preview edit the "
        "questions in place, since a form's questions are edited from a "
        "record that shows them",
    )
    input_preview = fields.Properties(
        definition="input_form_node_id.input_definition",
        string="Form Preview",
        copy=False,
        help="Add, reorder and edit the questions of this step's form here. "
        "What is filled in is a sample and reaches no run.",
    )
    step_references = fields.Json(
        compute="_compute_step_references",
        store=True,
        readonly=True,
        discloses="base.internal",
        help="The step keys this step names, parsed when its code is saved: "
        "checking a run reads them here, so it needs no right to read code",
    )
    step_reference_warning = fields.Text(
        compute="_compute_step_reference_warning",
        help="What this step reads of other steps that the graph does not "
        "guarantee has run; no run starts while it is set",
    )

    _step_key_uniq = models.UniqueIndex(
        "(automation_rule_id, step_key) WHERE step_key IS NOT NULL",
        "Another step of this automation already has this key.",
    )

    @api.constrains("node_type", "subflow_automation_id", "automation_rule_id")
    def _check_subflow(self) -> None:
        for action in self.filtered(lambda node: node.node_type == "subflow"):
            target = action.subflow_automation_id
            if not target:
                raise exceptions.ValidationError(
                    self.env._(
                        "Step '%(action)s' is a sub-workflow but names no "
                        "automation to run.",
                        action=action.name,
                    )
                )
            owner = action.automation_rule_id
            seen = self.env["automation.rule"]
            frontier = target
            while frontier:
                if frontier & owner:
                    raise exceptions.ValidationError(
                        self.env._(
                            "Step '%(action)s' would run automation '%(target)s', "
                            "which reaches back to '%(owner)s' -- a sub-workflow "
                            "cannot contain the workflow that runs it.",
                            action=action.name,
                            target=target.name,
                            owner=action.automation_rule_id.name,
                        )
                    )
                seen |= frontier
                frontier = frontier.action_server_ids.subflow_automation_id - seen

    @api.constrains("node_type", "approval_user_ids")
    def _check_approval_has_approvers(self) -> None:
        for action in self:
            if action.node_type == "approval" and not action.approval_user_ids:
                raise exceptions.ValidationError(
                    self.env._(
                        "Step '%(action)s' asks for approval but names nobody to "
                        "give it, so the workflow would wait forever.",
                        action=action.name,
                    )
                )

    @api.constrains("node_type", "input_field_ids", "input_definition")
    def _check_input_has_fields(self) -> None:
        for action in self.filtered(lambda node: node.node_type == "input"):
            asks_form = bool(action._get_form_questions())
            if not action.input_field_ids and not asks_form:
                raise exceptions.ValidationError(
                    self.env._(
                        "Step '%(action)s' asks for input but names no field to "
                        "fill in, so the workflow would wait forever.",
                        action=action.name,
                    )
                )
            if action.input_field_ids and asks_form:
                raise exceptions.ValidationError(
                    self.env._(
                        "Input step '%(action)s' asks both the run's fields and "
                        "a form of its own. Ask one of them, or split it into "
                        "two steps.",
                        action=action.name,
                    )
                )

    @api.constrains("step_key", "automation_rule_id")
    def _check_step_key(self) -> None:
        for action in self.filtered(lambda node: node.step_key):
            if not is_valid_step_key(action.step_key):
                raise exceptions.ValidationError(
                    self.env._(
                        "Step '%(action)s' has the key '%(key)s'. A key is "
                        "lowercase letters, digits and single underscores, "
                        "starts with a letter, is at most %(max)s characters "
                        "and is not a Python keyword nor one of: %(reserved)s.",
                        action=action.name,
                        key=action.step_key or "",
                        max=STEP_KEY_MAX,
                        reserved=", ".join(sorted(RESERVED_KEYS)),
                    )
                )

    @api.depends("automation_rule_id", "code", "state")
    def _compute_step_references(self) -> None:
        for action in self:
            action.step_references = (
                action._collect_step_references().to_json()
                if action.automation_rule_id
                else False
            )

    @api.depends(*STEP_REFERENCE_DEPENDS)
    def _compute_step_reference_warning(self) -> None:
        for action in self:
            action.step_reference_warning = (
                "\n".join(action._get_step_reference_problems())
                if action.automation_rule_id
                else False
            )

    @api.model_create_multi
    def create(self, vals_list):
        default_rule_id = self.env.context.get("default_automation_rule_id")
        keyless = [
            (vals, vals.get("automation_rule_id") or default_rule_id)
            for vals in vals_list
            if not vals.get("step_key")
        ]
        taken_by_rule: dict[int, set[str]] = defaultdict(set)
        rule_ids = {rule_id for _vals, rule_id in keyless if rule_id}
        if rule_ids:
            for node in self.search_fetch(
                [("automation_rule_id", "in", list(rule_ids))],
                ["automation_rule_id", "step_key"],
            ):
                taken_by_rule[node.automation_rule_id.id].add(node.step_key)
        for vals, rule_id in keyless:
            if not rule_id:
                continue
            taken = taken_by_rule[rule_id]
            vals["step_key"] = make_step_key(vals.get("name") or "", taken)
            taken.add(vals["step_key"])
        actions = super().create(vals_list)
        for action in actions.filtered("automation_rule_id"):
            action.input_form_node_id = action
        return actions

    def copy_data(self, default=None):
        default = dict(default or {})
        vals_list = super().copy_data(default)
        if "step_key" in default:
            return vals_list
        for action, vals in zip(self, vals_list, strict=True):
            if vals.get("automation_rule_id") == action.automation_rule_id.id:
                vals.pop("step_key", None)
        return vals_list

    def write(self, vals):
        if "step_key" in vals:
            self._check_key_not_referenced(vals["step_key"])
        result = super().write(vals)
        if vals.get("automation_rule_id") or "step_key" in vals:
            self._assign_missing_step_keys()
        return result

    def _assign_missing_step_keys(self) -> None:
        keyless = self.filtered(
            lambda node: node.automation_rule_id and not node.step_key
        )
        if not keyless:
            return
        taken: dict[int, set[str]] = defaultdict(set)
        for node in self.search_fetch(
            [("automation_rule_id", "in", keyless.automation_rule_id.ids)],
            ["automation_rule_id", "step_key"],
        ):
            taken[node.automation_rule_id.id].add(node.step_key)
        for action in keyless:
            rule_taken = taken[action.automation_rule_id.id]
            action.step_key = make_step_key(action.name or "", rule_taken)
            rule_taken.add(action.step_key)

    def unlink(self):
        self.exists()._check_key_not_referenced(False)
        return super().unlink()

    def _check_key_not_referenced(self, new_key) -> None:
        for action in self.filtered(
            lambda node: node.automation_rule_id and node.step_key != new_key,
        ):
            readers = [
                reader.name
                for reader in action.automation_rule_id.action_server_ids - self
                if action.step_key in reader._get_step_references().keys
            ] + [
                edge.display_name
                for edge in action.automation_rule_id.edge_ids
                if edge.source_node_id not in self
                and edge.target_node_id not in self
                and action.step_key in edge._get_step_references().keys
            ]
            if readers:
                raise exceptions.ValidationError(
                    self.env._(
                        "Step '%(action)s' is read as steps.%(key)s by: "
                        "%(readers)s. Change them first.",
                        action=action.name,
                        key=action.step_key,
                        readers=", ".join(readers),
                    )
                )

    def _get_form_questions(self) -> list[dict]:
        self.check_singleton()
        return [
            question
            for question in self.input_definition or []
            if question.get("type") != "separator"
        ]

    def _get_upstream_nodes(self):
        self.check_singleton()
        upstream = self.browse()
        frontier = self._get_predecessors()
        while frontier:
            upstream |= frontier
            frontier = frontier._get_predecessors() - upstream
        return upstream

    def _collect_step_references(self) -> References:
        self.check_singleton()
        if self.state != "code":
            return References()
        return collect_references(self.code)

    def _get_step_references(self) -> References:
        self.check_singleton()
        return References.from_json(self.step_references)

    def _get_step_reference_problems(self) -> list[str]:
        self.check_singleton()
        refs = self._get_step_references()
        problems = []
        predecessors = self._get_predecessors()
        if refs.uses_previous and len(predecessors) != 1:
            problems.append(
                self.env._(
                    "Step '%(action)s' reads `previous`, but %(count)s steps lead "
                    "to it. Name the one it means with steps.<key>.",
                    action=self.name,
                    count=len(predecessors),
                )
            )
        if not refs.keys:
            return problems
        siblings = {
            node.step_key: node for node in self.automation_rule_id.action_server_ids
        }
        upstream_keys = set(self._get_upstream_nodes().mapped("step_key"))
        for key in sorted(refs.keys - upstream_keys):
            node = siblings.get(key)
            if not node:
                problems.append(
                    self.env._(
                        "Step '%(action)s' uses step '%(key)s', and no step of "
                        "this automation has that key.",
                        action=self.name,
                        key=key,
                    )
                )
            elif node == self:
                problems.append(
                    self.env._(
                        "Step '%(action)s' uses steps.%(key)s, which is itself; "
                        "a step reads its own answers as `step`.",
                        action=self.name,
                        key=key,
                    )
                )
            else:
                problems.append(
                    self.env._(
                        "Step '%(action)s' uses step '%(other)s' (%(key)s), which "
                        "is not upstream of it, so it may not have run yet. "
                        "Connect '%(other)s' before '%(action)s'.",
                        action=self.name,
                        other=node.name,
                        key=key,
                    )
                )
        return problems

    @api.constrains("pos_width", "pos_height")
    def _check_canvas_size(self) -> None:
        for action in self:
            sizes = (("width", action.pos_width), ("height", action.pos_height))
            for axis, value in sizes:
                if not value:
                    continue
                if not NODE_SIZE_MIN[axis] <= value <= NODE_SIZE_MAX[axis]:
                    raise exceptions.ValidationError(
                        self.env._(
                            "The canvas %(axis)s of step '%(step)s' is %(value)s, "
                            "outside the %(minimum)s-%(maximum)s the canvas draws.\n\n"
                            "Use 0 to leave the step at the default size.",
                            axis=axis,
                            step=action.name or "?",
                            value=value,
                            minimum=NODE_SIZE_MIN[axis],
                            maximum=NODE_SIZE_MAX[axis],
                        )
                    )

    @api.constrains("node_type", "wait_delay")
    def _check_wait_delay(self) -> None:
        for action in self:
            if action.node_type == "wait" and action.wait_delay <= 0:
                raise exceptions.ValidationError(
                    self.env._(
                        "Step '%(action)s' waits for %(delay)s %(unit)s, which is "
                        "not a wait. Give it a positive duration.",
                        action=action.name,
                        delay=action.wait_delay,
                        unit=action.wait_unit,
                    )
                )

    @api.constrains("validity_delay", "start_delay")
    def _check_validity_delay(self) -> None:
        for action in self:
            if action.start_delay < 0:
                raise exceptions.ValidationError(
                    self.env._(
                        "Step '%(action)s' has a negative start delay.",
                        action=action.name,
                    ),
                )
            if action.validity_delay < 0:
                raise exceptions.ValidationError(
                    self.env._(
                        "Step '%(action)s' has a negative validity.",
                        action=action.name,
                    ),
                )

    def _get_start_delta(self):
        self.check_singleton()
        return get_timedelta(self.start_delay, self.start_delay_unit)

    def _get_validity_delta(self):
        self.check_singleton()
        return get_timedelta(self.validity_delay, self.validity_unit)

    def _get_line_input_fields(self):
        self.check_singleton()
        return self.line_input_field_ids

    def _render_approval_note(self, record) -> str:
        self.check_singleton()
        note = self.approval_note
        if not note:
            return self.name
        if not record:
            return note
        rendered = self.env["mixin.mail.render"]._render_template(
            note, record._name, [record.id]
        )
        return rendered.get(record.id) or self.name

    def _workflow_step_detail(self):
        if self.node_type == "input":
            return ", ".join(self.input_field_ids.mapped("field_description"))
        return ""

    def _prepare_workflow_node(self) -> dict:
        self.check_singleton()
        return {
            "id": self.id,
            "name": self.name,
            "step_key": self.step_key or "",
            "state": self.state,
            "node_type": self.node_type,
            "sequence": self.sequence,
            "pos_x": self.pos_x,
            "pos_y": self.pos_y,
            "width": self.pos_width or NODE_SIZE_DEFAULT["width"],
            "height": self.pos_height or NODE_SIZE_DEFAULT["height"],
            "wait_delay": self.wait_delay,
            "wait_unit": self.wait_unit,
            "approver_names": ", ".join(self.approval_user_ids.mapped("display_name")),
            "subflow_name": self.subflow_automation_id.display_name or "",
            "detail": self._workflow_step_detail(),
        }

    def _execute_runtime_lines(self, lines):
        self.check_singleton()
        for line in lines:
            line.action_execute()

    def _get_wait_delta(self):
        self.check_singleton()
        return get_timedelta(self.wait_delay, self.wait_unit)

    def _get_predecessors(self):
        return self.edge_in_ids.source_node_id

    def _get_successors(self):
        return self.edge_out_ids.target_node_id

    def _sorted_by_dependency(self):
        ordered_by_sequence = self.sorted("sequence")

        edges = {
            action.id: set(action._get_predecessors().ids) & set(self.ids)
            for action in ordered_by_sequence
        }
        if not any(edges.values()):
            return ordered_by_sequence

        remaining = list(ordered_by_sequence)
        settled: set[int] = set()
        ordered = self.browse()
        while remaining:
            ready = [a for a in remaining if edges[a.id] <= settled]
            if not ready:
                return ordered + self.browse([a.id for a in remaining])
            ordered += self.browse([a.id for a in ready])
            settled.update(a.id for a in ready)
            ready_ids = {a.id for a in ready}
            remaining = [a for a in remaining if a.id not in ready_ids]
        return ordered

    @api.depends("usage")
    def _compute_available_model_ids(self) -> None:
        super()._compute_available_model_ids()
        rule_based = self.filtered(lambda action: action.usage == "automation")
        for action in rule_based:
            rule_model = action.automation_rule_id.model_id
            action.available_model_ids = (
                rule_model.ids if rule_model in action.available_model_ids else []
            )

    def action_view_automation(self):
        return {
            "type": "ir.actions.act_window",
            "target": "current",
            "views": [[False, "form"]],
            "res_model": self.automation_rule_id._name,
            "res_id": self.automation_rule_id.id,
        }

    def _get_domain_children(self):
        return super()._get_domain_children() & Domain("automation_rule_id", "=", False)

    def _prepare_eval_context(self, action):
        eval_context = super()._prepare_eval_context(action)
        if action.state == "code":
            eval_context["json"] = json_scriptsafe
            line_id = self.env.context.get("runtime_line_id")
            if line_id:
                line = self.env["automation.runtime.line"].browse(line_id)
                eval_context["runtime_line"] = line
                eval_context["runtime"] = line.runtime_id
                eval_context.update(line._get_step_scope())
            elif runtime_id := self.env.context.get("runtime_id"):
                eval_context["runtime"] = self.env["automation.runtime"].browse(
                    runtime_id,
                )
        return eval_context

    def _get_warning_messages(self):
        self.check_singleton()
        warnings = super()._get_warning_messages()

        if (
            self.automation_rule_id
            and self.model_id != self.automation_rule_id.model_id
        ):
            warnings.append(
                self.env._(
                    "Model of action %(action_name)s should match the one from automated rule %(rule_name)s.",
                    action_name=self.name,
                    rule_name=self.automation_rule_id.name,
                ),
            )

        return warnings

    @api.model
    def _get_fields_warning_depends(self):
        return super()._get_fields_warning_depends() + [
            "model_id",
            "automation_rule_id",
        ]
