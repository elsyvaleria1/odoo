from __future__ import annotations

import typing
from collections import defaultdict
from typing import Any

from odoo import api, fields, models
from odoo.libs.documents import Document, format_offset

from ..tools.engines import can_transcribe
from .ir_attachment import TRANSCRIPT_STATES

if typing.TYPE_CHECKING:
    from odoo.addons.base.models.ir_attachment import IrAttachment
    from odoo.addons.media.models.media_segment import MediaSegment


class MixinMediaTimeline(models.AbstractModel):
    _inherit = "mixin.media.timeline"

    timeline_transcript = fields.Text(compute="_compute_timeline_transcript")
    timeline_transcript_state = fields.Selection(
        selection=TRANSCRIPT_STATES,
        compute="_compute_timeline_transcript_state",
    )

    timeline_speaker_ids = fields.Many2many(
        comodel_name="speech.speaker",
        string="Speakers",
        compute="_compute_timeline_speaker_ids",
    )

    @api.depends("segment_ids.attachment_id.speaker_ids")
    def _compute_timeline_speaker_ids(self) -> None:
        for record in self:
            record.timeline_speaker_ids = record.segment_ids.attachment_id.speaker_ids

    def _talk_time_by_person(self) -> dict:
        self.check_singleton()
        totals: dict = {}
        for speaker in self.timeline_speaker_ids:
            person = speaker.partner_id or speaker.label
            totals[person] = totals.get(person, 0.0) + speaker.talk_time_s
        return totals

    @api.depends("segment_ids.attachment_id.transcript_cues")
    def _compute_timeline_transcript(self) -> None:
        for record in self:
            spoken = [
                segment.attachment_id.transcript_text
                for segment in record.segment_ids.sorted("start_ms")
            ]
            record.timeline_transcript = "\n".join(part for part in spoken if part)

    @api.depends("segment_ids.attachment_id.transcript_state")
    def _compute_timeline_transcript_state(self) -> None:
        for record in self:
            states = set(record.segment_ids.attachment_id.mapped("transcript_state"))
            if "running" in states:
                record.timeline_transcript_state = "running"
            elif "queued" in states:
                record.timeline_transcript_state = "queued"
            elif "failed" in states:
                record.timeline_transcript_state = "failed"
            elif states and states == {"done"}:
                record.timeline_transcript_state = "done"
            else:
                record.timeline_transcript_state = "none"

    def _next_media_offset_ms(self) -> int:
        self.check_singleton()
        return self.media_duration_ms

    def _file_media(
        self,
        attachment: IrAttachment,
        start_ms: int | None = None,
        end_ms: int | None = None,
        *,
        eta: Any = None,
        priority: int | None = None,
    ) -> MediaSegment:
        self.check_singleton()
        if start_ms is None:
            start_ms = self._next_media_offset_ms()
        if end_ms is None:
            end_ms = start_ms + attachment._media_length_ms()
        segment = self._add_media_segment(
            attachment, start_ms, max(end_ms, start_ms + 1)
        )
        purpose = self._media_transcription_options().get("purpose")
        if can_transcribe(
            attachment.mimetype or "",
            self.env,
            purpose,
            attachment.company_id or None,
        ):
            attachment._transcribe_later(eta=eta, priority=priority)
        return segment

    def _spoken_lines(self) -> tuple[str, dict[str, models.Model]]:
        self.check_singleton()
        segments = self.segment_ids.sorted("start_ms")
        several = len(segments) > 1
        lines = []
        voices: dict[str, models.Model] = defaultdict(
            lambda: self.env["speech.speaker"]
        )
        for index, segment in enumerate(segments, 1):
            attachment = segment.attachment_id
            by_label = {speaker.label: speaker for speaker in attachment.speaker_ids}
            for cue in attachment.transcript_cues or []:
                words = (cue.get("text") or "").strip()
                if not words:
                    continue
                label = cue.get("speaker") or ""
                speaker = by_label.get(label)
                shown = _shown(speaker, label, index if several else 0)
                if speaker:
                    voices[shown] |= speaker
                at = segment.start_ms / 1000 + (cue.get("start") or 0.0)
                lines.append(
                    f"[{format_offset(at)}] {shown}: {words}"
                    if shown
                    else f"[{format_offset(at)}] {words}"
                )
        return "\n".join(lines), dict(voices)

    def _as_timeline_document(self, preamble: str = "") -> Document | None:
        self.check_singleton()
        text, _voices = self._spoken_lines()
        if not text:
            return None
        if preamble:
            text = f"{preamble}\n\n{text}"
        options = {}
        if "company_id" in self._fields and self.company_id:
            options["company"] = self.company_id
        return Document(
            text.encode(), "text/plain", f"{self.display_name}.txt", **options
        )

    def action_transcribe_media(self) -> None:
        for record in self:
            purpose = record._media_transcription_options().get("purpose")
            for segment in record.segment_ids:
                if can_transcribe(
                    segment.attachment_id.mimetype or "", self.env, purpose
                ):
                    segment.attachment_id._transcribe_later()

    def _media_transcription_options(self) -> dict:
        return {}

    def _as_transcript_owner(self):
        return self

    def _on_media_transcribed(self, attachment: IrAttachment) -> None:
        pass

    def _on_media_transcription_failed(self, attachment: IrAttachment) -> None:
        pass

    def _on_media_fully_transcribed(self) -> None:
        pass


def _shown(speaker: models.Model | None, label: str, segment: int) -> str:
    if speaker and speaker.partner_id:
        return speaker.partner_id.name
    if speaker and speaker.name and speaker.name != label:
        return speaker.name
    if label and segment:
        return f"{label}/{segment}"
    return label
