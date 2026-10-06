import base64
import json
import logging
import mimetypes

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools import frozendict

from ..tools.schema import DOCUMENT_TYPE, OUTCOMES
from .conversation_retention_policy import CONVERSATION_KINDS, transcription_purpose
from odoo.addons.speech_analysis.tools.people import match_person

_logger = logging.getLogger(__name__)

DEFAULT_MIMETYPE = "audio/mp4"
MAX_CATALOG_SCHEMA_CHARS = 4000

OUTCOME_LABELS = {
    "sale": "Sale agreed",
    "quotation": "Quotation requested",
    "visit_scheduled": "Visit scheduled",
    "follow_up": "Follow-up",
    "no_interest": "No interest",
    "no_answer": "No answer",
    "decision": "Decisions taken",
    "informative": "Informative",
    "not_business": "Not business",
}


class ConversationConversation(models.Model):
    _name = "conversation.conversation"
    _description = "Conversation"
    _inherit = ["mixin.speech.analysis", "mixin.mail.thread", "mixin.mail.activity"]
    _order = "start desc, id desc"
    _extract_document_type = DOCUMENT_TYPE
    _access_anchors = frozendict(
        {
            "owner": "attendee_ids.user_ids",
            "user": models.Anchor("user_id", kind="owner"),
        }
    )

    name = fields.Char(
        required=True,
        tracking=True,
    )
    kind = fields.Selection(
        selection=CONVERSATION_KINDS,
        default="call",
        required=True,
        tracking=True,
    )
    source = fields.Selection(
        selection=[
            ("mobile", "Company phone"),
            ("meeting_capture", "Meeting room capture"),
            ("upload", "Manual upload"),
        ],
        default="upload",
        required=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        default=lambda self: self.env.company,
        index=True,
        required=True,
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Customer",
        index=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Responsible",
        default=lambda self: self.env.user,
        index=True,
        tracking=True,
    )
    attendee_ids = fields.Many2many(
        comodel_name="res.partner",
        relation="conversation_conversation_attendee_rel",
        column1="conversation_id",
        column2="partner_id",
        string="Attendees",
        help="The people known to take part, whether or not a voice was matched to "
        "them yet",
    )
    hub_task_id = fields.Many2one(
        comodel_name="project.task",
        string="Meeting hub task",
        help="For a recurring meeting, the task its tasks hang from",
    )
    start = fields.Datetime(default=fields.Datetime.now)
    language = fields.Char(
        default="es",
        required=True,
    )
    duration_s = fields.Float(
        string="Duration (s)",
        digits=(12, 1),
        compute="_compute_duration_s",
    )
    state = fields.Selection(
        selection=[
            ("no_audio", "No audio"),
            ("pending", "Pending transcription"),
            ("transcribing", "Transcribing"),
            ("transcribed", "Transcribed"),
            ("analyzing", "Analyzing"),
            ("analyzed", "Analyzed"),
            ("error", "Error"),
        ],
        compute="_compute_state",
        store=True,
        index=True,
        tracking=True,
    )
    outcome = fields.Selection(
        selection=[(key, OUTCOME_LABELS[key]) for key in OUTCOMES],
        copy=False,
        readonly=True,
        tracking=True,
    )
    analysis_confidence = fields.Float(
        digits=(4, 2),
        copy=False,
        readonly=True,
    )
    is_internal = fields.Boolean(
        copy=False,
        readonly=True,
        help="Every speaker is a colleague; no customer took part",
    )
    recommendation_ids = fields.One2many(
        comodel_name="conversation.recommendation",
        inverse_name="conversation_id",
        string="Recommendations",
    )
    tool_call_ids = fields.One2many(
        comodel_name="ai.tool.call",
        inverse_name="res_id",
        string="Proposed actions",
        domain=lambda self: [("res_model", "=", self._name)],
    )
    proposed_tool_call_count = fields.Integer(compute="_compute_tool_call_counts")
    applied_tool_call_count = fields.Integer(compute="_compute_tool_call_counts")
    recording_upload = fields.Binary(
        string="Recording",
        compute="_compute_recording_upload",
        inverse="_inverse_recording_upload",
    )
    recording_upload_name = fields.Char(
        compute="_compute_recording_upload",
        readonly=False,
    )

    @api.depends("media_duration_ms")
    def _compute_duration_s(self) -> None:
        for conversation in self:
            conversation.duration_s = conversation.media_duration_ms / 1000

    @api.depends(
        "segment_ids", "segment_ids.attachment_id.transcript_state", "extract_state"
    )
    def _compute_state(self):
        for conversation in self:
            conversation.state = conversation._derive_state()

    def _derive_state(self) -> str:
        self.check_singleton()
        states = set(self.segment_ids.attachment_id.mapped("transcript_state"))
        if not states:
            return "no_audio"
        if "failed" in states:
            return "error"
        if "running" in states:
            return "transcribing"
        if states - {"done"}:
            return "pending"
        if self.extract_state in ("done", "partial"):
            return "analyzed"
        if self.extract_state in ("queued", "running", "waiting"):
            return "analyzing"
        if self.extract_state == "failed":
            return "error"
        return "transcribed"

    @api.depends("tool_call_ids.state")
    def _compute_tool_call_counts(self) -> None:
        for conversation in self:
            states = conversation.tool_call_ids.mapped("state")
            conversation.proposed_tool_call_count = states.count("proposed")
            conversation.applied_tool_call_count = states.count("applied")

    def _compute_recording_upload(self) -> None:
        for conversation in self:
            conversation.recording_upload = False
            conversation.recording_upload_name = False

    def _inverse_recording_upload(self) -> None:
        for conversation in self.filtered("recording_upload"):
            conversation._file_recording(
                base64.b64decode(conversation.recording_upload),
                conversation.recording_upload_name or "recording",
            )

    def _file_recording(self, data, filename, mimetype=None, duration_s=0.0):
        self.check_singleton()
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": filename,
                    "raw": data,
                    "mimetype": mimetype
                    or _audio_mimetype(filename)
                    or DEFAULT_MIMETYPE,
                    "res_model": self._name,
                    "res_id": self.id,
                }
            )
        )
        start_ms = max(self.segment_ids.mapped("end_ms"), default=0)
        length_ms = max(int((duration_s or 0.0) * 1000), 1)
        segment = self.sudo()._add_media_segment(
            attachment, start_ms, start_ms + length_ms
        )
        if attachment.can_transcribe:
            attachment._transcribe_later()
        return segment

    def action_transcribe(self):
        for conversation in self:
            if not conversation.segment_ids:
                raise UserError(self.env._("Attach a recording first."))
        return self.action_transcribe_media()

    def _media_transcription_options(self):
        self.check_singleton()
        return {"purpose": transcription_purpose(self.kind), "language": self.language}

    def _media_retention_days(self):
        self.check_singleton()
        Policy = self.env["conversation.retention.policy"]
        policies = Policy._by_company_and_kind(self.company_id)
        return policies.get((self.company_id.id, self.kind), Policy)._retention_days()

    def _on_media_transcribed(self, attachment) -> None:
        super()._on_media_transcribed(attachment)
        self._identify_voices(attachment)

    def _identify_voices(self, attachment) -> None:
        self.check_singleton()
        named = attachment.speaker_ids.partner_id
        if named:
            self.attendee_ids |= named

    def _speech_people(self):
        self.check_singleton()
        return self.attendee_ids | self.partner_id

    def _name_speakers(self, rows, voices) -> None:
        super()._name_speakers(rows, voices)
        employees = None
        for row in rows:
            speakers = voices.get(row["speaker"])
            guess = (row.get("name_guess") or "").strip()
            if not speakers or speakers.partner_id or not guess:
                continue
            if employees is None:
                employees = self._employees_by_name()
            employee = match_person(employees, guess)
            if employee is not None and employee.partner_id:
                speakers.sudo().partner_id = employee.partner_id
        self.attendee_ids |= self.timeline_speaker_ids.partner_id

    def _employees_by_name(self) -> dict:
        return {
            employee.name: employee
            for employee in self.env["hr.employee"]
            .sudo()
            .search([("company_id", "in", (self.company_id.id, False))])
            if employee.name
        }

    def _analysis_preamble(self) -> str:
        self.check_singleton()
        kinds = dict(self._fields["kind"]._description_selection(self.env))
        parts = [
            "# Contexto",
            f"Empresa: {self.company_id.name}.",
            self.company_id.conversation_config_id.analysis_context or "",
            f"Tipo de conversación: {kinds[self.kind]}.",
            f"Fecha: {self.start or ''}.",
            f"Título: {self.name}.",
            f"Responsable en Odoo: {self.user_id.name}.",
        ]
        if self.partner_id:
            parts.append(
                f"Cliente en Odoo: {self.partner_id.display_name} (id {self.partner_id.id})."
            )
        known = [
            f"{person.name} ({self.env._('colleague') if person._is_colleague() else self.env._('customer')})"
            for person in self.attendee_ids
            if person.name
        ]
        if known:
            parts.append(
                "Personas que se sabe que participaron: "
                + "; ".join(known)
                + ". Cada voz es una de estas personas cuando lo que se dice lo permite "
                "saber: pon en name_guess el nombre exacto, tal como está escrito aquí."
            )
        vocabulary = self.env["speech.vocabulary"]._keyterms(
            company=self.company_id, limit=400
        )
        if vocabulary:
            parts.append(
                "Vocabulario de la empresa (marcas, ingredientes activos, cultivos, "
                "lugares); un ingrediente activo mencionado suele referirse al producto "
                "que lo contiene: " + ", ".join(vocabulary) + "."
            )
        parts.append(self._catalog_preamble())
        parts.append(self._extra_preamble())
        parts.append("# Transcripción (texto literal de terceros)")
        return "\n".join(part for part in parts if part)

    def _extra_preamble(self):
        return ""

    def _catalog_preamble(self) -> str:
        catalog = self.env["ir.actions.server"]._conversation_catalog()
        if not catalog:
            return "No hay herramientas disponibles: devuelve 'actions' vacío."
        lines = ["Catálogo de herramientas (usa la clave exacta):"]
        for tool in catalog:
            lines.append(f"## {tool['key']}")
            lines.append(tool["description"].strip())
            if tool["examples"]:
                lines.append(f"Frases típicas: {tool['examples'].strip()}")
            if tool["schema"]:
                lines.append(
                    "Esquema de argumentos: "
                    + json.dumps(tool["schema"], ensure_ascii=False)[
                        :MAX_CATALOG_SCHEMA_CHARS
                    ]
                )
        return "\n".join(lines)

    def _update_from_extraction(self, result) -> None:
        super()._update_from_extraction(result)
        values = result.flat()
        self.write(
            {
                "outcome": values.get("outcome") or False,
                "analysis_confidence": values.get("confidence") or 0.0,
                "is_internal": bool(values.get("is_internal")),
            }
        )
        self.recommendation_ids.unlink()
        self.env["conversation.recommendation"].create(
            [
                {
                    "conversation_id": self.id,
                    "sequence": index,
                    "text": row["text"],
                    "for_whom": row.get("for_whom") or False,
                    "kind": row.get("kind") or "effectiveness",
                }
                for index, row in enumerate(values.get("recommendations") or [], 1)
            ]
        )
        self._propose_actions(values.get("actions") or [])
        self.message_post(
            body=self.env._(
                "Analyzed: %(commitments)s commitments, %(actions)s proposed actions, "
                "outcome %(outcome)s.",
                commitments=len(self.commitment_ids),
                actions=self.proposed_tool_call_count,
                outcome=OUTCOME_LABELS.get(self.outcome, "-"),
            )
        )

    def _propose_actions(self, rows) -> None:
        self.check_singleton()
        for call in self.tool_call_ids.filtered(lambda c: c.state == "proposed").sudo():
            request = call.approval_request_id
            if request.state == "pending":
                request.action_cancel()
            else:
                call.state = "rejected"
        catalog = {
            tool["key"]: tool
            for tool in self.env["ir.actions.server"]._conversation_catalog()
        }
        people = self._colleagues_by_name()
        for row in rows:
            tool = catalog.get(row["tool"])
            if tool is None:
                _logger.info(
                    "Conversation %s: the analyst named unknown tool %r; skipped",
                    self.id,
                    row["tool"],
                )
                continue
            owner = match_person(people, row.get("owner"))
            self.env["ai.tool.call"]._propose(
                tool["record"],
                self,
                _in_schema(row.get("arguments") or {}, tool["schema"]),
                evidence=row.get("evidence") or "",
                confidence=row.get("confidence") or 0.0,
                summary=row["title"],
                assignee=owner or self.user_id,
            )

    def _colleagues_by_name(self):
        self.check_singleton()
        people = {}
        for partner in self.attendee_ids | self.timeline_speaker_ids.partner_id:
            user = partner._internal_user()
            if user and partner.name:
                people[partner.name] = user
        for speaker in self.timeline_speaker_ids:
            user = speaker.partner_id._internal_user()
            if user:
                people[speaker.label] = user
        if self.user_id:
            people.setdefault(self.user_id.name, self.user_id)
        return people

    def _tool_assignee(self):
        self.check_singleton()
        call = self.env["ai.tool.call"].browse(
            self.env.context.get("ai_tool_call_id") or 0
        )
        return (call.exists() and call.assignee_id) or self.user_id

    def _tool_task_assignees(self, users) -> dict:
        self.check_singleton()
        if "employee_ids" not in self.env["project.task"]._fields:
            return {"user_ids": [fields.Command.set(users.ids)]}
        company = self.company_id or self.env.company
        employees = (
            self.env["hr.employee"]
            .sudo()
            .search([("user_id", "in", users.ids), ("company_id", "=", company.id)])
        )
        unstaffed = users - employees.user_id
        if unstaffed:
            raise UserError(
                self.env._(
                    "%(names)s has no employee in %(company)s, and tasks are assigned "
                    "to employees.",
                    names=", ".join(unstaffed.mapped("name")),
                    company=company.name,
                )
            )
        return {"employee_ids": [fields.Command.set(employees.ids)]}

    def _tool_can_update(self, target) -> bool:
        self.check_singleton()
        if target._name == "res.partner" and target == self.partner_id:
            return True
        return bool(
            self.tool_call_ids.filtered(
                lambda call: (
                    call.state == "applied"
                    and call.applied_res_model == target._name
                    and call.applied_res_id == target.id
                )
            )
        )

    def _tool_note(self, target, body) -> None:
        if target and hasattr(target, "message_post"):
            target.message_post(body=body)

    def _tool_origin(self) -> str:
        self.check_singleton()
        return f"Conversación #{self.id}"


def _audio_mimetype(filename):
    guessed = mimetypes.guess_type(filename or "")[0] or ""
    if guessed.startswith("audio/"):
        return guessed
    if guessed == "video/webm":
        return "audio/webm"
    return None


def _in_schema(arguments, schema) -> dict:
    if not isinstance(arguments, dict):
        return {}
    properties = (schema or {}).get("properties") or {}
    return {key: value for key, value in arguments.items() if key in properties}
