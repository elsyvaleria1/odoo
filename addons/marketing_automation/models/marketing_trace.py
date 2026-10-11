from odoo import api, fields, models

OUTSTANDING_LINE_STATES = ("waiting", "scheduled", "ready", "paused", "in_progress")


def trace_state_of(line) -> str:
    if line.state == "done":
        return "processed"
    if line.state == "error":
        return "error"
    if line.state == "skipped" and line.skip_reason == "filtered":
        return "rejected"
    if line.state in ("skipped", "cancel"):
        return "canceled"
    return "scheduled"


class MarketingTrace(models.Model):
    _name = "marketing.trace"
    _description = "Marketing Trace"
    _order = "schedule_date DESC, id ASC"
    _rec_name = "participant_id"

    line_id = fields.Many2one(
        comodel_name="automation.runtime.line",
        string="Workflow Step",
        index=True,
        readonly=True,
        required=True,
        ondelete="cascade",
    )
    participant_id = fields.Many2one(
        comodel_name="marketing.participant",
        index=True,
        required=True,
        ondelete="cascade",
    )
    res_id = fields.Integer(
        related="participant_id.res_id",
        string="Document ID",
        readonly=False,
    )
    is_test = fields.Boolean(
        related="participant_id.is_test",
        string="Test Trace",
        readonly=True,
    )
    activity_id = fields.Many2one(
        comodel_name="marketing.activity",
        index=True,
        required=True,
        ondelete="cascade",
    )
    activity_type = fields.Selection(
        related="activity_id.activity_type",
        readonly=True,
    )
    trigger_type = fields.Selection(
        related="activity_id.trigger_type",
        readonly=True,
    )

    state = fields.Selection(
        selection=[
            ("scheduled", "Scheduled"),
            ("processed", "Processed"),
            ("rejected", "Rejected"),
            ("canceled", "Cancelled"),
            ("error", "Error"),
        ],
        compute="_compute_state",
        inverse="_inverse_state",
        store=True,
        index=True,
        readonly=False,
    )
    schedule_date = fields.Datetime(
        compute="_compute_schedule_date",
        inverse="_inverse_schedule_date",
        store=True,
        readonly=False,
    )
    state_msg = fields.Text(
        related="line_id.error_message",
        string="Error message",
        readonly=False,
    )
    parent_id = fields.Many2one(
        comodel_name="marketing.trace",
        compute="_compute_parent_id",
        store=True,
        index=True,
    )
    child_ids = fields.One2many(
        comodel_name="marketing.trace",
        inverse_name="parent_id",
        string="Direct child traces",
    )
    mailing_trace_ids = fields.One2many(
        comodel_name="mailing.trace",
        inverse_name="marketing_trace_id",
        string="Mass mailing statistics",
    )
    mailing_trace_status = fields.Selection(
        related="mailing_trace_ids.trace_status",
        readonly=True,
    )
    links_click_datetime = fields.Datetime(compute="_compute_links_click_datetime")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("line_id"):
                vals["line_id"] = self._create_line(vals).id
        return super().create(vals_list)

    @api.model
    def _create_line(self, vals):
        participant = self.env["marketing.participant"].browse(vals["participant_id"])
        activity = self.env["marketing.activity"].browse(vals["activity_id"])
        return (
            self.env["automation.runtime.line"]
            .sudo()
            .create(
                {
                    "runtime_id": participant.runtime_id.id,
                    "action_id": activity.node_id.id,
                    "name": activity.name,
                    "state": "waiting",
                }
            )
        )

    @api.depends("line_id.state", "line_id.skip_reason")
    def _compute_state(self):
        for trace in self:
            trace.state = trace_state_of(trace.line_id)

    def _inverse_state(self) -> None:
        for trace in self:
            if trace.state != trace_state_of(trace.line_id):
                trace._settle_line(trace.state)

    @api.depends(
        "line_id.state",
        "line_id.date_resume",
        "line_id.date_ready",
        "line_id.date_settled",
    )
    def _compute_schedule_date(self) -> None:
        for trace in self:
            line = trace.line_id
            if line.state in OUTSTANDING_LINE_STATES:
                trace.schedule_date = line.date_resume or line.date_ready or False
            elif line.skip_reason == "filtered":
                trace.schedule_date = line.date_resume or line.date_settled
            else:
                trace.schedule_date = line.date_settled

    def _inverse_schedule_date(self) -> None:
        for trace in self:
            line = trace.line_id.sudo()
            if line.state in OUTSTANDING_LINE_STATES:
                line.date_resume = trace.schedule_date
                if trace.schedule_date and line.state in ("waiting", "ready"):
                    line.state = "scheduled"
            else:
                line.date_settled = trace.schedule_date

    @api.depends("line_id.edge_in_ids.source_line_id")
    def _compute_parent_id(self) -> None:
        for trace in self:
            sources = trace.line_id.edge_in_ids.source_line_id
            trace.parent_id = sources.marketing_trace_ids[:1]

    @api.depends("mailing_trace_ids")
    def _compute_links_click_datetime(self) -> None:
        self.links_click_datetime = False
        mailing_trace = self.filtered(lambda x: x.mailing_trace_ids)
        for trace in mailing_trace:
            trace.links_click_datetime = trace.mailing_trace_ids[0].links_click_datetime

    def _settle_line(self, state, message=False, advance=True) -> None:
        lines = self.line_id.sudo()
        outstanding = lines.filtered(lambda line: line.state in OUTSTANDING_LINE_STATES)
        if state == "processed":
            outstanding.action_mark_done()
        elif state == "error":
            outstanding.action_mark_error(message or False)
        elif state == "rejected":
            due_by_line = {line: line.date_resume for line in outstanding}
            outstanding._skip(reason="filtered", message=message)
            for line, due in due_by_line.items():
                if due:
                    line.date_resume = due
        elif state == "canceled":
            outstanding.write(
                {
                    "state": "cancel",
                    "date_resume": False,
                    "date_settled": self.env.cr.now(),
                }
            )
            outstanding._activate_successors()
            outstanding.edge_out_ids.target_line_id._create_missing_marketing_traces()
        if message:
            lines.filtered(
                lambda line: line.error_message != message
            ).error_message = message
        if advance:
            lines.runtime_id._advance()

    def participant_action_cancel(self) -> None:
        self.action_cancel(message=self.env._("Manually"))

    def action_cancel(self, message=None):
        for trace in self:
            line = trace.line_id.sudo()
            if line.state in OUTSTANDING_LINE_STATES:
                line._skip(reason="cancelled", message=message)
            elif message:
                line.error_message = message
        self.line_id.runtime_id.sudo()._advance()

    def action_execute(self):
        for activity, traces in self.grouped("activity_id").items():
            lines = traces.line_id.sudo().filtered(
                lambda line: line.state in ("waiting", "scheduled", "ready"),
            )
            lines.filtered(lambda line: line.state != "ready").action_mark_ready()
            activity._execute_lines(lines)
        self.line_id.runtime_id.sudo()._advance()

    def _get_exclusive_events(self):
        return {"mail_bounce"}

    def _get_event_cancel_messages(self) -> dict:
        return {
            "mail_open": self.env._("Parent activity mail opened"),
            "mail_reply": self.env._("Parent activity mail replied"),
            "mail_click": self.env._("Parent activity mail clicked"),
            "mail_bounce": self.env._("Parent activity mail bounced"),
        }

    def process_event(self, action) -> bool | None:
        self.check_singleton()
        if self.participant_id.campaign_id.state not in ["draft", "running"]:
            return None
        line = self.line_id.sudo()
        outstanding = line.edge_out_ids.target_line_id.filtered(
            lambda target: target.state in OUTSTANDING_LINE_STATES,
        )
        line._receive_event(action, exclusive=action in self._get_exclusive_events())
        message = self._get_event_cancel_messages().get(action)
        if message:
            outstanding.filtered(lambda target: target.state == "skipped").write(
                {"error_message": message}
            )
        released = line.edge_out_ids.target_line_id.filtered(
            lambda target: target.state == "ready",
        )
        for node, lines in released.grouped("action_id").items():
            node._execute_runtime_lines(lines)
        released.runtime_id._advance()
        return True
