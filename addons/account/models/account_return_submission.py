from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.libs.debug_log import DebugLog
from odoo.tools import frozendict

_debug = DebugLog(__name__)

JOB_CHANNEL = "account_return_filing"
STATUS_POLL_SECONDS = 600
STATUS_POLL_ATTEMPTS = 288
OPEN_STATES = ("sending", "acknowledged")


class AccountReturnSubmission(models.Model):
    _name = "account.return.submission"
    _access_anchors = frozendict(
        {
            "company": models.Anchor("return_id.company_ids", shared=False),
        }
    )
    _inherit = ["mixin.mail.thread"]
    _description = "Tax Return Submission"
    _order = "id desc"

    return_id = fields.Many2one(
        comodel_name="account.return",
        index=True,
        required=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        related="return_id.company_id",
    )
    channel = fields.Selection(
        selection=[("manual", "Filed outside Odoo")],
        required=True,
        tracking=True,
    )
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("sending", "Sending"),
            ("acknowledged", "Acknowledged"),
            ("accepted", "Accepted"),
            ("rejected", "Rejected"),
            ("error", "Error"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    is_test = fields.Boolean(
        string="Test Submission",
        help="Sent to the authority's test environment; it files nothing.",
    )
    external_ref = fields.Char(
        string="Authority Reference",
        tracking=True,
        help="The identifier the authority gave this filing: an acknowledgement number, "
        "a correlation id, an operation number.",
    )
    date_sent = fields.Datetime(readonly=True)
    date_accepted = fields.Datetime(readonly=True)
    request_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="What Was Sent",
        readonly=True,
    )
    receipt_attachment_ids = fields.Many2many(
        comodel_name="ir.attachment",
        relation="account_return_submission_receipt_rel",
        string="Receipts",
    )
    error_payload = fields.Json(readonly=True)
    error_message = fields.Text(compute="_compute_error_message")
    rectifies_id = fields.Many2one(
        comodel_name="account.return.submission",
        string="Rectifies",
        index="btree_not_null",
        readonly=True,
    )
    line_ids = fields.One2many(
        comodel_name="account.return.submission.line",
        inverse_name="submission_id",
        string="Amounts Filed",
    )

    @api.depends("error_payload")
    def _compute_error_message(self) -> None:
        for submission in self:
            submission.error_message = submission._get_error_message()

    def _get_error_message(self) -> str:
        self.check_singleton()
        payload = self.error_payload or {}
        errors = payload.get("errors") or []
        lines = [payload["message"]] if payload.get("message") else []
        lines += [
            f"[{error['code']}] {error['message']}"
            if error.get("code")
            else error["message"]
            for error in errors
        ]
        return "\n".join(lines)

    def _get_channel(self):
        self.check_singleton()
        return self.env[f"account.return.filing.{self.channel}"]

    def _check_writable_fields(self, vals) -> None:
        mutable_after_acceptance = {
            "receipt_attachment_ids",
            "message_main_attachment_id",
        }
        if set(vals) - mutable_after_acceptance and self.filtered(
            lambda submission: submission.state == "accepted"
        ):
            raise UserError(
                self.env._(
                    "An accepted submission is what the authority holds; it cannot change. "
                    "File a rectification instead."
                )
            )

    def write(self, vals):
        self._check_writable_fields(vals)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_accepted(self) -> None:
        if self.filtered(lambda submission: submission.state == "accepted"):
            raise UserError(self.env._("An accepted submission cannot be deleted."))

    @_debug.perf.timed
    def action_send(self) -> dict | None:
        _debug.lifecycle("action_send", records=self)
        self.check_singleton()
        if self.state not in ("draft", "error", "sending"):
            raise UserError(
                self.env._("Only a draft or failed submission can be sent.")
            )
        action = self._get_channel()._send_submission(self)
        if action:
            return action
        self._after_channel_answer()
        return None

    def _after_channel_answer(self) -> None:
        self.check_singleton()
        _debug.logic("submission_answered", submission=self, state=self.state)
        if self.state == "accepted":
            self.return_id._on_submission_accepted(self)
        elif self.state == "acknowledged":
            self._poll_later()

    def _poll_later(self) -> None:
        self.check_singleton()
        self.delayed(
            channel=JOB_CHANNEL,
            eta=STATUS_POLL_SECONDS,
            identity_key=f"account.return.submission.{self.id}.status",
            name=f"Tax filing status: {self.return_id.display_name}",
        )._job_update_status()

    @api.job(channel=JOB_CHANNEL, max_retries=3, max_defers=STATUS_POLL_ATTEMPTS)
    def _job_update_status(self) -> None:
        self.check_singleton()
        if self.state not in OPEN_STATES:
            return
        self._get_channel()._update_submission_status(self)
        if self.state in OPEN_STATES:
            self.env["ir.job"]._defer(
                STATUS_POLL_SECONDS,
                reason=f"{self.channel} has not answered for {self.external_ref or self.id}",
            )
            return
        if self.state == "accepted":
            self.return_id._on_submission_accepted(self)

    def _update_from_channel(self, state, **values) -> None:
        self.check_singleton()
        vals = {"state": state, **values}
        if state == "accepted" and "date_accepted" not in vals:
            vals["date_accepted"] = fields.Datetime.now()
        if state in ("sending", "acknowledged") and not self.date_sent:
            vals.setdefault("date_sent", fields.Datetime.now())
        self.write(vals)
