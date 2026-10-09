from __future__ import annotations

import logging
import typing
from typing import Any, Self

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Domain
from odoo.libs.documents import CUES, Cue, Document, cues_as_text, extension_for

from ..tools.engines import (
    DEFAULT_SPEECH_MIMETYPE,
    can_transcribe,
    is_recording,
    synthesis_engines,
)

if typing.TYPE_CHECKING:
    from odoo.addons.base.models.ir_attachment_reading import IrAttachmentReading

_logger = logging.getLogger(__name__)

JOB_CHANNEL = "speech"

TRANSCRIPT_STATES = [
    ("none", "Not transcribed"),
    ("queued", "Queued"),
    ("running", "Transcribing"),
    ("done", "Transcribed"),
    ("failed", "Failed"),
]


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    # a transcript is the file's `cues` reading (base ir.attachment.reading);
    # these fields read it
    transcript_state = fields.Selection(
        selection=TRANSCRIPT_STATES,
        compute="_compute_transcript",
        search="_search_transcript_state",
        compute_sudo=True,
    )
    transcript_cues = fields.Json(
        compute="_compute_transcript",
        compute_sudo=True,
        help="What is said in this recording, with the moment each phrase "
        "starts and ends.",
    )
    transcript_language = fields.Char(
        compute="_compute_transcript",
        compute_sudo=True,
    )
    transcript_engine = fields.Char(
        compute="_compute_transcript",
        compute_sudo=True,
    )
    transcript_error = fields.Text(
        compute="_compute_transcript",
        compute_sudo=True,
    )
    transcript_text = fields.Text(compute="_compute_transcript_text")
    can_transcribe = fields.Boolean(compute="_compute_can_transcribe")
    speaker_ids = fields.One2many(
        comodel_name="speech.speaker",
        inverse_name="attachment_id",
        string="Speakers",
    )

    @api.depends(
        "checksum",
        "mimetype",
        "reading_ids.representation",
        "reading_ids.state",
        "reading_ids.value",
        "reading_ids.read_by",
        "reading_ids.language",
        "reading_ids.error",
        "reading_ids.checksum",
    )
    def _compute_transcript(self) -> None:
        # only a recording is ever transcribed: the rest need not read the
        # readings at all
        recordings = self.filtered(lambda a: is_recording(a.mimetype or ""))
        (self - recordings).update(
            {
                "transcript_state": "none",
                "transcript_cues": False,
                "transcript_language": False,
                "transcript_engine": False,
                "transcript_error": False,
            }
        )
        for attachment in recordings:
            reading = attachment._reading(CUES)
            done = reading.state == "done"
            attachment.transcript_state = reading.state or "none"
            attachment.transcript_cues = reading.value if done else False
            attachment.transcript_language = reading.language or False
            attachment.transcript_engine = reading.read_by if done else False
            attachment.transcript_error = (
                reading.error if reading.state == "failed" else False
            )

    def _search_transcript_state(self, operator: str, value: Any) -> Domain:
        if operator not in ("in", "not in"):
            return NotImplemented
        states = set(value)
        Reading = self.env["ir.attachment.reading"].with_privilege(
            "base.privilege_keep_readings",
            reason="find recordings by where their transcript stands",
        )
        found = Domain(
            "id",
            "in",
            Reading._search(
                [("representation", "=", CUES), ("state", "in", list(states))]
            ).subselect("attachment_id"),
        )
        if "none" in states:
            found |= Domain(
                "id",
                "not in",
                Reading._search([("representation", "=", CUES)]).subselect(
                    "attachment_id"
                ),
            )
        return found if operator == "in" else ~found

    @api.depends("transcript_cues")
    def _compute_transcript_text(self) -> None:
        for attachment in self:
            attachment.transcript_text = cues_as_text(attachment._transcript_cues())

    @api.depends("mimetype", "company_id")
    def _compute_can_transcribe(self) -> None:
        self.can_transcribe = False
        recordings = self.filtered(lambda a: is_recording(a.mimetype or ""))
        if not recordings:
            return
        purposes = recordings._transcript_purposes()
        readable = {}
        for attachment in recordings:
            company = attachment.company_id or self.env.company
            purpose = purposes.get(attachment.id)
            key = (attachment.mimetype, company, purpose)
            if key not in readable:
                readable[key] = can_transcribe(
                    attachment.mimetype or "",
                    self.with_company(company).env,
                    purpose,
                )
            attachment.can_transcribe = readable[key]

    def _transcript_purposes(self) -> dict[int, str | None]:
        segments = (
            self.env["media.segment"].sudo().search([("attachment_id", "in", self.ids)])
        )
        options_by_owner = {}
        purposes = {}
        for segment in segments:
            owner = segment._owner()
            if owner is None or not hasattr(owner, "_media_transcription_options"):
                continue
            key = (owner._name, owner.id)
            if key not in options_by_owner:
                options_by_owner[key] = owner._media_transcription_options()
            purposes[segment.attachment_id.id] = options_by_owner[key].get("purpose")
        return purposes

    def _transcript_cues(self) -> list[Cue]:
        self.check_singleton()
        return [
            Cue(
                start=cue.get("start", 0.0),
                end=cue.get("end", 0.0),
                text=cue.get("text", ""),
                speaker=cue.get("speaker", ""),
                confidence=cue.get("confidence", 0.0),
            )
            for cue in self.transcript_cues or []
        ]

    def _transcript_vtt(self) -> str:
        self.check_singleton()
        cues = self._transcript_cues()
        return Document.of(cues=cues).data.decode() if cues else ""

    def action_transcribe(self) -> bool:
        spoken = self.filtered("can_transcribe")
        if not spoken:
            raise UserError(
                self.env._(
                    "Nothing here can be transcribed: either the file is not a "
                    "recording, or no speech engine is installed."
                )
            )
        for attachment in spoken:
            attachment._transcribe_later()
        return True

    def _transcribe_later(
        self,
        language: str | None = None,
        priority: int | None = None,
        eta: Any = None,
    ) -> Any:
        return self._read_later(
            CUES, eta=eta, priority=priority, channel=JOB_CHANNEL, language=language
        )

    # jobs queued before transcripts became readings still name this method
    @api.job(channel=JOB_CHANNEL, max_retries=1)
    def _job_transcribe(self, language: str | None = None) -> None:
        self.check_singleton()
        self._read(CUES, language=language)

    def _transcribe(
        self, language: str | None = None, prompt: str | None = None
    ) -> list[Cue] | None:
        cues = self._read(CUES, language=language, prompt=prompt)
        return cues if self._reading(CUES).state == "done" else None

    def _read(self, representation: str, **options: Any) -> Any:
        # a recording is heard under its owner's purpose; captions a file
        # carries (vtt, srt) are read like any other representation
        if representation != CUES or not is_recording(self.mimetype or ""):
            return super()._read(representation, **options)
        self.check_singleton()
        owner = self._transcript_owner_options()
        given = {key: value for key, value in options.items() if value}
        options = {
            **owner,
            **given,
            "language": given.get("language")
            or self._reading(CUES).language
            or owner.get("language")
            or None,
        }
        company = self.company_id or self.env.company
        if not can_transcribe(
            self.mimetype or "", self.with_company(company).env, options.get("purpose")
        ):
            raise UserError(
                self.env._(
                    "No speech engine reads %(mimetype)s.",
                    mimetype=self.mimetype or "?",
                )
            )
        return super()._read(CUES, **options)

    def _on_read(self, representation: str, reading: IrAttachmentReading) -> None:
        super()._on_read(representation, reading)
        if representation != CUES:
            return
        if reading.state == "done":
            self.env["speech.speaker"]._sync_from_cues(self)
        elif reading.state == "failed":
            _logger.warning(
                "Could not transcribe attachment %s: %s", self.id, reading.error
            )
        if reading.state in ("done", "failed"):
            self._notify_transcript_owner(transcribed=reading.state == "done")

    def _transcript_owner_options(self) -> dict[str, Any]:
        self.check_singleton()
        segment = self._transcript_segments(limit=1)
        owner = segment._owner() if segment else None
        if owner is None or not hasattr(owner, "_as_transcript_owner"):
            return {}
        return owner._as_transcript_owner()._media_transcription_options()

    def _transcript_segments(self, limit: int | None = None):
        # whoever queued the transcript, the timeline it was heard on is told
        return (
            self.env["media.segment"]
            .with_privilege(
                "speech.privilege_find_transcript_owner",
                reason="a transcript tells the timeline it was heard on",
            )
            .search([("attachment_id", "=", self.id)], limit=limit)
        )

    def _notify_transcript_owner(self, transcribed: bool) -> None:
        self.check_singleton()
        for segment in self._transcript_segments():
            owner = segment._owner()
            if owner is None or not hasattr(owner, "_as_transcript_owner"):
                continue
            owner = owner._as_transcript_owner()
            if transcribed:
                owner._on_media_transcribed(self)
                if owner.timeline_transcript_state == "done":
                    owner._on_media_fully_transcribed()
            else:
                owner._on_media_transcription_failed(self)

    @api.model
    def _speech_synthesize(
        self,
        text: str,
        *,
        voice: str | None = None,
        language: str | None = None,
        mimetype: str = DEFAULT_SPEECH_MIMETYPE,
        name: str | None = None,
        res_model: str | None = None,
        res_id: int | None = None,
        **options: Any,
    ) -> Self:
        if not (text or "").strip():
            raise UserError(self.env._("There is nothing to read aloud."))
        engines = synthesis_engines(mimetype, self.env)
        if not engines:
            raise UserError(
                self.env._("No speech engine writes %(mimetype)s.", mimetype=mimetype)
            )
        audio = engines[0].write(
            text,
            env=self.env,
            voice=voice,
            language=language,
            **options,
        )
        return self.create(
            {
                "name": name or self._speech_filename(mimetype),
                "raw": audio,
                "mimetype": mimetype,
                "res_model": res_model,
                "res_id": res_id,
            }
        )

    @api.model
    def _speech_filename(self, mimetype: str) -> str:
        extension = extension_for(mimetype) or mimetype.rsplit("/", 1)[-1]
        stamp = fields.Datetime.now().strftime("%Y-%m-%d-%H%M%S")
        return f"Speech-{stamp}.{extension}"
