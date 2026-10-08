from odoo import api, fields, models


class MediaSegment(models.Model):
    _inherit = "media.segment"

    transcript_state = fields.Selection(
        related="attachment_id.transcript_state",
        string="Transcription",
    )
    transcript_cues = fields.Json(related="attachment_id.transcript_cues")
    transcript_speakers = fields.Json(
        compute="_compute_transcript_speakers",
        compute_sudo=True,
        help="The name each voice of the transcript is shown under, by its label.",
    )
    live = fields.Boolean(
        readonly=True,
        help="A chunk sent during a live capture, transcribed as soon as it arrives.",
    )

    # a cue keeps the label the transcriber gave it; the person put on that
    # voice is shown instead wherever one has been
    @api.depends("attachment_id.speaker_ids.label", "attachment_id.speaker_ids.name")
    def _compute_transcript_speakers(self) -> None:
        for segment in self:
            segment.transcript_speakers = {
                speaker.label: speaker.name
                for speaker in segment.attachment_id.speaker_ids
                if speaker.name
            }
