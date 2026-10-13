from odoo import fields, models


class AIComposer(models.Model):
    _name = "ai.composer"
    _inherit = ["ai.composer"]

    interface_key = fields.Selection(
        selection_add=[
            (
                "voice_transcription_component",
                "Summary Buttons for Voice Transcription Component",
            )
        ],
        ondelete={"voice_transcription_component": "cascade"},
    )
