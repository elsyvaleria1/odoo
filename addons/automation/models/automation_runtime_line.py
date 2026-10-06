import logging
from collections import defaultdict

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import frozendict

from ._input import INPUT_CONTEXT_KEY, add_input_fields, add_input_form
from ._steps import NoPrevious, StepScope, StepView
from .workflow_edge import EVENT_CONDITIONS, SETTLED_STATES

_logger = logging.getLogger(__name__)


class AutomationRuntimeLine(models.Model):
    _name = "automation.runtime.line"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("runtime_id.company_ids", shared=False),
        }
    )
    _description = "Automation Runtime Action Line"
    _order = "sequence, id"

    runtime_id = fields.Many2one(
        comodel_name="automation.runtime",
        string="Workflow Runtime",
        index=True,
        required=True,
        ondelete="cascade",
    )
    action_id = fields.Many2one(
        comodel_name="ir.actions.server",
        string="Server Action",
        required=True,
        ondelete="restrict",
        help="The server action to execute",
    )
    name = fields.Char(
        string="Step Name",
        required=True,
        help="Description of this workflow step",
    )
    sequence = fields.Integer(
        default=10,
        help="Execution order (lower = earlier)",
    )
    state = fields.Selection(
        selection=[
            ("waiting", "Waiting"),
            ("scheduled", "Scheduled"),
            ("ready", "Ready"),
            ("paused", "Paused"),
            ("in_progress", "In Progress"),
            ("done", "Done"),
            ("skipped", "Skipped"),
            ("cancel", "Cancelled"),
            ("error", "Error"),
        ],
        default="waiting",
        copy=False,
        readonly=True,
        required=True,
        help="Action execution state",
    )
    activity_ids = fields.One2many(
        comodel_name="mail.activity",
        inverse_name="automation_runtime_line_id",
        string="Approval Activities",
        readonly=True,
    )
    date_resume = fields.Datetime(
        string="Resumes At",
        copy=False,
        readonly=True,
        help="When a scheduled step becomes ready, or a paused Wait step completes",
    )
    date_ready = fields.Datetime(
        string="Ready Since",
        copy=False,
        readonly=True,
        help="When the step became ready; its validity counts from here",
    )
    date_settled = fields.Datetime(
        string="Settled At",
        copy=False,
        readonly=True,
        help="When the step finished, failed, was skipped or was cancelled; "
        "a delayed edge out of it counts from here",
    )
    skip_reason = fields.Selection(
        selection=[
            ("branch", "Branch not taken"),
            ("revoked", "Revoked by an exclusive event"),
            ("expired", "Validity passed"),
            ("filtered", "Filtered out"),
            ("cancelled", "Cancelled"),
        ],
        copy=False,
        readonly=True,
    )
    error_message = fields.Text(
        string="Error Details",
        readonly=True,
        help="Error message if execution failed",
    )

    edge_in_ids = fields.One2many(
        comodel_name="automation.runtime.edge",
        inverse_name="target_line_id",
        string="Waits For",
        help="Edges that must be satisfied before this step can execute",
    )

    edge_out_ids = fields.One2many(
        comodel_name="automation.runtime.edge",
        inverse_name="source_line_id",
        string="Enables",
        readonly=True,
        help="Edges this step's outcome can satisfy",
    )

    created_record_ref = fields.Reference(
        selection="_selection_created_record_models",
        string="Created Record",
        readonly=True,
        help="Record created or modified by this action",
    )
    output = fields.Json(
        copy=False,
        readonly=True,
        help="What the step reports it did, as data. An edge leaving the step "
        "reads it as `output` in its expression.",
    )
    output_summary = fields.Char(
        string="Result",
        copy=False,
        readonly=True,
        help="What the step reports it did, in words",
    )
    input_values = fields.Properties(
        definition="action_id.input_definition",
        string="Answers",
        copy=False,
        help="This run's answers to the step's form; later steps read them as "
        "steps.<key>.input",
    )

    @api.model
    def _selection_created_record_models(self):
        return [
            ("automation.runtime", "Workflow Runtime"),
        ]

    def _get_missing_inputs(self):
        """Return the fields of this step it needs filled before it runs and lacks."""
        self.check_singleton()
        return self.action_id._get_line_input_fields().filtered(
            lambda field: field.name in self._fields and not self[field.name],
        )

    def _get_unanswered_questions(self) -> list[str]:
        """Return the labels of this step's form questions still unanswered.

        A yes/no question is answered by being left unticked.
        """
        self.check_singleton()
        answers = self.input_values
        return [
            question.get("string") or question["name"]
            for question in self.action_id._get_form_questions()
            if question.get("type") != "boolean"
            and _is_blank(answers.get(question["name"]))
        ]

    def _asks_before_running(self) -> bool:
        self.check_singleton()
        return bool(self._get_missing_inputs() or self._get_unanswered_questions())

    def _awaits_input(self) -> bool:
        """Whether someone must fill in fields before this step goes on.

        An Input step waits on its run's fields or its form; any other step
        paused itself because its own fields or form were empty when it was
        reached. Every other pause waits on a clock, an approval or a
        sub-workflow.
        """
        self.check_singleton()
        if self.state != "paused":
            return False
        if self.action_id.node_type in ("input", "action"):
            return True
        return not (
            self.date_resume
            or self.activity_ids
            or (
                self.created_record_ref
                and self.created_record_ref._name == "automation.runtime"
            )
        )

    @api.model
    def _get_input_fields(self):
        """Return the fields the step named by the context needs filled."""
        line = self.browse(self.env.context.get(INPUT_CONTEXT_KEY)).exists()
        return (
            line.action_id._get_line_input_fields().filtered(
                lambda field: field.name in self._fields,
            )
            if line
            else self.env["ir.model.fields"]
        )

    @api.model
    def _input_line_has_form(self) -> bool:
        line = self.browse(self.env.context.get(INPUT_CONTEXT_KEY)).exists()
        return bool(line and line.action_id._get_form_questions())

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type="form", **options):
        key = super()._get_view_cache_key(view_id, view_type, **options)
        return key + (
            tuple(self._get_input_fields().mapped("name")),
            self._input_line_has_form(),
        )

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        input_view = self.env.ref(
            "automation.view_automation_runtime_line_form_input",
            raise_if_not_found=False,
        )
        if view_type == "form" and view == input_view:
            add_input_fields(arch, self._get_input_fields())
            if self._input_line_has_form():
                add_input_form(arch)
        return arch, view

    def _get_input_action(self) -> dict:
        self.check_singleton()
        return {
            "type": "ir.actions.act_window",
            "name": self.name,
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "automation.view_automation_runtime_line_form_input"
                    ).id,
                    "form",
                ),
            ],
            "target": "new",
            "context": {INPUT_CONTEXT_KEY: self.id},
        }

    def action_submit_input(self) -> dict:
        self.check_singleton()
        if not self._awaits_input() or (
            self.action_id.node_type == "input" and self.action_id.input_field_ids
        ):
            raise UserError(
                self.env._(
                    "This step of '%(run)s' is no longer waiting for input.",
                    run=self.runtime_id.name,
                ),
            )
        missing = [
            *self._get_missing_inputs().mapped("field_description"),
            *self._get_unanswered_questions(),
        ]
        if missing:
            raise UserError(
                self.env._(
                    "'%(step)s' still needs: %(fields)s",
                    step=self.name,
                    fields=", ".join(missing),
                ),
            )
        runtime = self.runtime_id
        if runtime.state == "waiting_resume":
            runtime.state = "in_progress"
        if self.action_id.node_type == "input":
            self.action_resume()
            runtime._log_run_message(
                body=self.env._("'%(step)s' received its input.", step=self.name),
                subject=self.env._("Input Received"),
            )
            runtime._advance()
            runtime._notify_workflow_change()
            return {"type": "ir.actions.act_window_close"}
        self.state = "ready"
        # The dialog was part of pressing Next Step on this step: it runs this
        # step, as Next Step would have, and no more.
        result = runtime._run_line(self)
        if isinstance(result, dict):
            return result
        return {"type": "ir.actions.act_window_close"}

    def _set_output(self, output: dict, summary: str = "") -> None:
        """Record what the step did: data for the flow, and a line for people."""
        self.write({"output": output, "output_summary": summary or False})

    def action_run(self) -> dict | None:
        """Run this ready step now, whichever other steps are ready too."""
        self.check_singleton()
        runtime = self.runtime_id
        if self.state != "ready" or runtime.state not in (
            "in_progress",
            "waiting_resume",
        ):
            raise UserError(
                self.env._(
                    "'%(step)s' is not ready to run in '%(run)s'.",
                    step=self.name,
                    run=runtime.name,
                ),
            )
        if runtime.state == "waiting_resume":
            runtime.state = "in_progress"
        result = runtime._run_line(self)
        return result if isinstance(result, dict) else None

    def _get_upstream_lines(self):
        """Return every step of the run this one transitively waits for."""
        self.check_singleton()
        upstream = self.browse()
        frontier = self._get_predecessors()
        while frontier:
            upstream |= frontier
            frontier = frontier._get_predecessors() - upstream
        return upstream

    def _get_step_views(self, lines) -> dict[str, StepView]:
        return {
            line.action_id.step_key: StepView(line)
            for line in lines
            if line.action_id.step_key
        }

    def _get_step_scope(self) -> dict:
        """Return the variables a code step evaluates with: what it may read
        of the other steps of its run, which is what runs before it."""
        self.check_singleton()
        views = self._get_step_views(self._get_upstream_lines())
        predecessors = self._get_predecessors()
        direct = {
            key: view
            for key, view in views.items()
            if key in set(predecessors.action_id.mapped("step_key"))
        }
        if len(direct) == 1:
            previous = next(iter(direct.values()))
        else:
            previous = NoPrevious(
                self.env._(
                    "'%(step)s' has %(count)s preceding steps (%(keys)s), so "
                    "`previous` names none of them: use steps.<key>.",
                    step=self.name,
                    count=len(predecessors),
                    keys=", ".join(sorted(direct)) or self.env._("none"),
                )
            )
        return {
            "steps": StepScope(views, self.name),
            "predecessors": StepScope(direct, self.name),
            "previous": previous,
            "step": StepView(self),
        }

    def _get_readable_steps(self) -> StepScope:
        """Return this step and everything upstream of it, as an edge leaving
        it reads them."""
        self.check_singleton()
        return StepScope(
            self._get_step_views(self | self._get_upstream_lines()),
            self.name,
        )

    def _predecessors_satisfied(self) -> bool:
        self.check_singleton()
        return all(edge._is_satisfied() for edge in self.edge_in_ids)

    def _get_predecessors(self):
        return self.edge_in_ids.source_line_id

    def _get_successors(self):
        return self.edge_out_ids.target_line_id

    def action_mark_ready(self, due=None) -> None:
        self.write(
            {
                "state": "ready",
                "date_ready": self.env.cr.now(),
                "date_resume": due or False,
                "error_message": False,
            }
        )

    def _is_expired(self) -> bool:
        self.check_singleton()
        action = self.action_id
        return bool(
            action.validity_delay
            and self.date_ready
            and self.date_ready + action._get_validity_delta() < self.env.cr.now()
        )

    def action_cancel(self):
        lines = self.filtered(
            lambda line: line.state not in ("done", "skipped", "cancel"),
        )
        lines.write({"state": "cancel", "date_settled": self.env.cr.now()})
        for line in lines.filtered("created_record_ref"):
            if line.created_record_ref._name == "automation.runtime":
                line.created_record_ref.action_cancel()

    def _activate_successors(self) -> None:
        self.edge_out_ids.target_line_id.filtered(
            lambda successor: successor.state in ("waiting", "scheduled"),
        )._settle_readiness()

    def _settle_readiness(self) -> None:
        if not self:
            return
        now = self.env.cr.now()
        edges = self.edge_in_ids
        edges.fetch(
            [
                "source_line_id",
                "condition",
                "condition_expr",
                "event_code",
                "delay",
                "delay_unit",
                "date_event",
                "revoked",
            ]
        )
        edges.source_line_id.fetch(["state", "date_settled"])
        decided = defaultdict(self.browse)
        for line in self:
            decision = line._readiness_decision(now)
            if decision:
                decided[decision] |= line
        for (kind, value), lines in decided.items():
            if kind == "skip":
                lines._skip(reason=value)
            elif kind == "wait":
                lines.write({"state": "waiting", "date_resume": False})
            elif kind == "schedule":
                lines._schedule(value)
            else:
                lines.action_mark_ready(due=value)

    def _readiness_decision(self, now):
        self.check_singleton()
        edges = self.edge_in_ids
        if not edges:
            due = self._start_due()
            return ("schedule", due) if due and due > now else ("ready", due)
        if any(edge.source_line_id.state not in SETTLED_STATES for edge in edges):
            return None
        live = edges.filtered(lambda edge: edge.source_line_id.state != "skipped")
        verdicts = [edge._verdict(now) for edge in live]
        if not live or any(satisfied is False for satisfied, _due in verdicts):
            return ("skip", "revoked" if any(live.mapped("revoked")) else "branch")
        if any(satisfied is None for satisfied, _due in verdicts):
            return ("wait", None) if self.state == "scheduled" else None
        due = max((due for _satisfied, due in verdicts if due), default=None)
        return ("schedule", due) if due and due > now else ("ready", due)

    def _start_due(self):
        self.check_singleton()
        action = self.action_id
        if not action.start_delay:
            return None
        return (self.create_date or self.env.cr.now()) + action._get_start_delta()

    def _skip(self, reason="branch", message=False) -> None:
        self.write(
            {
                "state": "skipped",
                "skip_reason": reason,
                "date_resume": False,
                "date_settled": self.env.cr.now(),
                "error_message": message,
            }
        )
        self._activate_successors()

    def _schedule(self, due) -> None:
        self.write({"state": "scheduled", "date_resume": due})
        self._trigger_resume_at(due)

    def _trigger_resume_at(self, due) -> None:
        triggered = self.env.cr.precommit.data.setdefault_set(
            "automation.resume_triggers"
        )
        if due in triggered:
            return
        triggered.add(due)
        self.env["ir.cron"]._trigger_ref(
            "automation.ir_cron_data_automation_resume", at=due
        )

    def _awaits_event(self) -> bool:
        self.check_singleton()
        return any(
            edge.condition == "event"
            and not edge.date_event
            and not edge.revoked
            and edge.source_line_id.state in ("done", "error", "cancel")
            for edge in self.edge_in_ids
        )

    def _receive_event(self, code, exclusive=False) -> None:
        now = self.env.cr.now()
        for line in self:
            edges = line.edge_out_ids
            received = edges.filtered(
                lambda edge: (
                    edge.condition in EVENT_CONDITIONS
                    and edge.event_code == code
                    and not edge.date_event
                ),
            )
            if not received and not exclusive:
                continue
            received.date_event = now
            if exclusive:
                (edges - received).revoked = True
            runtime = line.runtime_id
            if runtime.state not in ("in_progress", "waiting_resume"):
                continue
            line._activate_successors()
            runtime._advance()

    def _has_error_handler(self) -> bool:
        self.check_singleton()
        return any(
            edge.condition in ("on_error", "always") for edge in self.edge_out_ids
        )

    def _contains_its_error(self):
        self.check_singleton()
        return (
            self._has_error_handler()
            or self.runtime_id.automation_id.step_error_policy == "close_branch"
        )

    def action_pause(self):
        resume_at = self.env.cr.now() + self.action_id._get_wait_delta()
        self.write(
            {"state": "paused", "date_resume": resume_at, "error_message": False}
        )
        self._trigger_resume_at(resume_at)
        _logger.info(
            "Step '%s' (#%d) paused until %s",
            self.name,
            self.id,
            resume_at,
        )

    def action_request_approval(self) -> None:
        self.check_singleton()
        record = self.runtime_id._get_target_record()
        if not record:
            self.action_mark_error(
                self.env._(
                    "Approval cannot be requested: this run has no target record."
                ),
            )
            self.runtime_id.action_error()
            return

        activity_type = self.env.ref("mail.mail_activity_data_todo", False)
        summary = self.action_id.approval_note or self.name
        self.env["mail.activity"].create(
            [
                {
                    "res_model_id": self.env["ir.model"]._get_id(record._name),
                    "res_id": record.id,
                    "activity_type_id": activity_type.id if activity_type else False,
                    "summary": summary,
                    "user_id": approver.id,
                    "automation_runtime_line_id": self.id,
                }
                for approver in self.action_id.approval_user_ids
            ]
        )
        self.write({"state": "paused", "date_resume": False, "error_message": False})
        return

    def action_request_input(self) -> dict:
        self.check_singleton()
        self.write({"state": "paused", "date_resume": False, "error_message": False})
        return self.runtime_id._get_input_action(self)

    def action_start_subflow(self) -> None:
        self.check_singleton()
        parent = self.runtime_id
        child = self.env["automation.runtime"].create(
            {
                "automation_id": self.action_id.subflow_automation_id.id,
                "company_ids": [Command.set(parent.company_ids.ids)],
                "res_model": parent.res_model,
                "res_id": parent.res_id,
                "parent_line_id": self.id,
            }
        )
        self.write(
            {
                "state": "paused",
                "date_resume": False,
                "error_message": False,
                "created_record_ref": f"automation.runtime,{child.id}",
            }
        )
        child._launch()

    def action_refuse_approval(self, reason=False) -> None:
        for line in self.filtered(lambda step: step.state == "paused"):
            activities = line.activity_ids.filtered("active")
            runtime = line.runtime_id
            if runtime.state == "waiting_resume":
                runtime.state = "in_progress"
            line.action_mark_error(reason or self.env._("Approval was refused."))
            activities.unlink()
            if line._contains_its_error():
                runtime._advance()
            else:
                runtime.action_error()

    def _fail_missing_approval(self) -> None:
        for line in self.filtered(
            lambda step: (
                step.state == "paused"
                and step.action_id.node_type == "approval"
                and not step.activity_ids.filtered("active")
            ),
        ):
            runtime = line.runtime_id
            if runtime.state == "waiting_resume":
                runtime.state = "in_progress"
            line.action_mark_error(
                self.env._(
                    "The approval activity was removed before anyone acted on it."
                ),
            )
            if line._contains_its_error():
                runtime._advance()
            else:
                runtime.action_error()

    def _check_approval_complete(self) -> None:
        approvals = self.filtered(
            lambda step: (
                step.state == "paused" and step.action_id.node_type == "approval"
            ),
        )
        for line in approvals:
            if line.activity_ids.filtered("active"):
                continue
            runtime = line.runtime_id
            if runtime.state == "waiting_resume":
                runtime.state = "in_progress"
            line.action_resume()
            runtime._advance()

    def action_resume(self):
        paused = self.filtered(lambda step: step.state == "paused")
        paused.write(
            {
                "state": "done",
                "date_resume": False,
                "date_settled": self.env.cr.now(),
            }
        )
        paused._activate_successors()

    def action_mark_done(self):
        self.write(
            {"state": "done", "date_settled": self.env.cr.now(), "error_message": False}
        )
        self._activate_successors()
        self.runtime_id._finish_if_settled()

    def action_mark_error(self, error_msg):
        self.write(
            {
                "state": "error",
                "date_settled": self.env.cr.now(),
                "error_message": error_msg,
            }
        )
        self.filtered(lambda line: line._contains_its_error())._activate_successors()

    def action_execute(self):
        self.check_singleton()

        if self.state not in ("ready", "in_progress"):
            raise UserError(self.env._("Action is not ready to execute"))

        if self._is_expired():
            action = self.action_id
            units = dict(
                action._fields["validity_unit"]._description_selection(self.env)
            )
            self._skip(
                reason="expired",
                message=self.env._(
                    "Skipped: it became ready at %(ready)s, and its validity of "
                    "%(delay)s %(unit)s had passed when it came to run.",
                    ready=self.date_ready,
                    delay=action.validity_delay,
                    unit=units.get(action.validity_unit, action.validity_unit),
                ),
            )
            self.runtime_id._finish_if_settled()
            return False

        if self.action_id.node_type != "input" and self._asks_before_running():
            self.write(
                {"state": "paused", "date_resume": False, "error_message": False}
            )
            return self.runtime_id._get_input_action(self)

        if self.action_id.node_type == "wait":
            return self.action_pause()

        if self.action_id.node_type == "approval":
            return self.action_request_approval()

        if self.action_id.node_type == "input":
            return self.action_request_input()

        if self.action_id.node_type == "subflow":
            return self.action_start_subflow()

        self.write({"state": "in_progress"})

        try:
            ctx = dict(self.env.context)
            runtime = self.runtime_id
            if runtime.res_model and runtime.res_id:
                ctx.update(
                    {
                        "active_model": runtime.res_model,
                        "active_id": runtime.res_id,
                        "active_ids": [runtime.res_id],
                        "runtime_line_id": self.id,
                        "runtime_id": runtime.id,
                    }
                )
            else:
                ctx.update(
                    {
                        "active_model": "automation.runtime",
                        "active_id": runtime.id,
                        "active_ids": [runtime.id],
                        "runtime_line_id": self.id,
                        "runtime_id": runtime.id,
                    }
                )

            _logger.info(
                "Executing action '%s' (#%d) for runtime %s",
                self.name,
                self.action_id.id,
                self.runtime_id.name,
            )

            # Settling the step belongs to the step: releasing its successors
            # or closing the run can raise too, and a step left `error` with
            # its document still there would create a second one on retry.
            with self.env.cr.savepoint():
                result = self.action_id.with_context(**ctx).run()
                self.action_mark_done()

            _logger.info("✓ Action '%s' completed successfully", self.name)

            return result or True

        except Exception as e:
            error_msg = str(e)
            _logger.exception(
                "✗ Action '%s' failed: %s",
                self.name,
                error_msg,
            )

            self.action_mark_error(error_msg)
            if not self._contains_its_error():
                self.runtime_id.action_error()
            return False

    def _workflow_step_detail(self) -> str:
        self.check_singleton()
        return self.action_id._workflow_step_detail()

    def _get_created_record_label(self) -> str:
        self.check_singleton()
        record = self.created_record_ref and self.created_record_ref.exists()
        if not record:
            return ""
        return record._visible_display_names().get(record.id) or ""

    def _prepare_workflow_node(self) -> dict:
        self.check_singleton()
        return {
            "name": self.name,
            "line_id": self.id,
            "runtime_state": self.state,
            "deletable": False,
            "error_message": self.error_message or "",
            "created_record": self._get_created_record_label(),
            "output_summary": self.output_summary or "",
            "detail": self._workflow_step_detail(),
        }

    def action_view_document(self):
        self.check_singleton()

        if not self.created_record_ref:
            raise UserError(self.env._("No document created by this action"))

        return {
            "name": self.env._("Created Record"),
            "type": "ir.actions.act_window",
            "res_model": self.created_record_ref._name,
            "view_mode": "form",
            "res_id": self.created_record_ref.id,
        }


def _is_blank(value) -> bool:
    if isinstance(value, models.BaseModel):
        return not value
    return value is None or value is False or value in ("", [])
