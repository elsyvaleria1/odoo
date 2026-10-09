import json
import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.libs.json import loads as json_loads
from odoo.tools import frozendict

_logger = logging.getLogger(__name__)

DECIDED = frozenset(
    {
        "tool_id",
        "res_model",
        "res_id",
        "requester_id",
        "state",
        "applied_res_model",
        "applied_res_id",
        "error",
    }
)


class AiToolCall(models.Model):
    _name = "ai.tool.call"
    _inherit = ["mixin.mail.thread", "mixin.approval.gate", "mixin.owner.access"]
    _description = "AI Tool Call"
    _order = "id desc"
    _access_verbs = {"apply": models.Verb(methods=("action_apply",))}
    _access_owner_field = "res_id"
    _access_anchors = frozendict(
        {
            "owner": "approval_pending_user_ids",
        }
    )

    name = fields.Char(
        compute="_compute_name",
        store=True,
    )
    tool_id = fields.Many2one(
        comodel_name="ir.actions.server",
        index=True,
        required=True,
        ondelete="restrict",
    )
    tool_name = fields.Char(
        compute="_compute_tool_name",
        store=True,
    )
    res_model = fields.Char(
        string="Subject Model",
        index="btree_not_null",
        required=True,
    )
    res_id = fields.Many2oneReference(
        model_field="res_model",
        string="Subject",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
    )
    requester_id = fields.Many2one(
        comodel_name="res.users",
        string="Proposed for",
        default=lambda self: self.env.user,
    )
    summary = fields.Char(help="What the agent says the call does")
    arguments = fields.Json()
    arguments_text = fields.Text(
        string="Arguments",
        compute="_compute_arguments_text",
        inverse="_inverse_arguments_text",
    )
    evidence = fields.Text()
    confidence = fields.Float(digits=(4, 2))
    assignee_id = fields.Many2one(
        comodel_name="res.users",
        string="Assigned to",
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("proposed", "Proposed"),
            ("approved", "Approved"),
            ("applied", "Applied"),
            ("rejected", "Rejected"),
            ("failed", "Failed"),
        ],
        default="proposed",
        index=True,
        required=True,
        tracking=True,
    )
    applied_res_model = fields.Char(readonly=True)
    applied_res_id = fields.Many2oneReference(
        model_field="applied_res_model",
        readonly=True,
    )
    error = fields.Text(readonly=True)

    @api.depends("tool_id")
    def _compute_tool_name(self) -> None:
        for call in self:
            call.tool_name = call.tool_id.sudo().name

    @api.depends("tool_name", "summary", "res_model", "res_id")
    def _compute_name(self):
        for call in self:
            subject = call._subject()
            what = call.summary or call.tool_name
            call.name = f"{what}: {subject.sudo().display_name}" if subject else what

    @api.depends("arguments")
    def _compute_arguments_text(self) -> None:
        for call in self:
            call.arguments_text = json.dumps(
                call.arguments or {}, ensure_ascii=False, indent=2
            )

    def _inverse_arguments_text(self) -> None:
        for call in self:
            try:
                arguments = json_loads(call.arguments_text or "{}")
            except ValueError as error:
                raise UserError(
                    self.env._("Arguments must be valid JSON: %s", error)
                ) from error
            if not isinstance(arguments, dict):
                raise UserError(self.env._("Arguments must be a JSON object."))
            call.arguments = arguments

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            for vals in vals_list:
                self._refuse_decided(vals.keys())
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su:
            self._refuse_decided(vals.keys())
            if {"arguments", "arguments_text"} & vals.keys() and self.filtered(
                lambda call: call.state not in ("proposed", "failed")
            ):
                raise UserError(
                    self.env._("Only a call that has not run may change its arguments.")
                )
        return super().write(vals)

    def _refuse_decided(self, keys) -> None:
        touched = DECIDED & set(keys)
        if touched:
            raise AccessError(
                self.env._(
                    "%(fields)s are set by the agent and the approval, not by hand.",
                    fields=", ".join(sorted(touched)),
                )
            )

    def _subject(self):
        self.check_singleton()
        if not self.res_model or self.res_model not in self.env:
            return None
        return self.env[self.res_model].browse(self.res_id).exists() or None

    @api.model
    def _propose(
        self,
        tool,
        record,
        arguments,
        evidence="",
        confidence=0.0,
        summary="",
        assignee=None,
    ):
        values = {
            "tool_id": tool.id,
            "summary": summary or False,
            "assignee_id": assignee.id if assignee else False,
            "res_model": record._name if record is not None else tool.model_id.model,
            "res_id": record[:1].id if record else 0,
            "requester_id": self.env.uid,
            "arguments": dict(arguments or {}),
            "evidence": evidence or False,
            "confidence": confidence,
        }
        if record and "company_id" in record._fields and record[:1].company_id:
            values["company_id"] = record[:1].company_id.id
        call = self.sudo().create(values).with_env(self.env)
        try:
            with self.env.cr.savepoint():
                call.action_apply()
        except UserError as error:
            _logger.info("AI tool call %s could not be sent on: %s", call.id, error)
            call.sudo().message_post(
                body=self.env._("Could not be sent for approval: %s", error)
            )
        return call

    def _get_proposal_answer(self) -> str:
        self.check_singleton()
        if self.state == "applied":
            return self.env._("Done: %(name)s.", name=self.name)
        if self.state == "failed":
            return self.env._(
                "%(name)s failed: %(error)s", name=self.name, error=self.error
            )
        return self.env._(
            "%(name)s was proposed and waits for a person to approve it; it has "
            "not been done.",
            name=self.name,
        )

    def action_apply(self):
        return self._apply(self)

    def _apply(self, calls):
        for call in calls:
            call._apply_one()
        return True

    def _apply_one(self) -> None:
        self.check_singleton()
        if self.state == "applied":
            return
        runner = self.assignee_id or self.requester_id or self.create_uid
        companies = runner.sudo().company_ids
        company = (
            self.company_id
            if self.company_id in companies
            else runner.sudo().company_id
        )
        context = {
            "ai_tool_call_id": self.id,
            "allowed_company_ids": (company | companies).ids,
        }
        tool = self.tool_id.with_user(runner).sudo().with_context(**context)
        subject = self._subject()
        record = (
            (subject if subject is not None else self.env[self.res_model])
            .with_user(runner)
            .with_context(**context)
        )
        try:
            with self.env.cr.savepoint():
                result = tool._ai_tool_run(record, dict(self.arguments or {}))
        except Exception as error:
            _logger.info("AI tool call %s failed: %s", self.id, error, exc_info=True)
            self.sudo().write({"state": "failed", "error": str(error)})
            return
        values = {"state": "applied", "error": False}
        if isinstance(result, dict) and result.get("model") and result.get("id"):
            values["applied_res_model"] = result["model"]
            values["applied_res_id"] = result["id"]
        self.sudo().write(values)

    def _get_domain_approval_category(self):
        category = self.tool_id.sudo().ai_approval_category_id
        return [("id", "=", category.id)] if category else []

    def _get_approval_snapshot(self, operation):
        self.check_singleton()
        return {
            "tool": self.tool_id.id,
            "subject": [self.res_model, self.res_id],
            "arguments": self.arguments or {},
        }

    def _get_approval_reason_html(self):
        self.check_singleton()
        return self.env._(
            "An AI agent proposes %(name)s with %(arguments)s. %(evidence)s",
            name=self.name,
            arguments=self.arguments_text,
            evidence=self.evidence or "",
        )

    def _on_approval_approved(self) -> None:
        self.sudo().write({"state": "approved"})
        super()._on_approval_approved()

    def _on_approval_refused(self) -> None:
        self.sudo().write({"state": "rejected"})
        super()._on_approval_refused()

    def _on_approval_cancelled(self) -> None:
        self.sudo().write({"state": "rejected"})
        super()._on_approval_cancelled()
