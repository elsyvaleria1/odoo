from odoo.tools.module_data import move_xmlids


def migrate(cr, version):
    if not version:
        return
    move_xmlids(
        cr,
        [
            "ai_prompt_transcription_summarize_recruitment_call",
            "ai_prompt_transcription_summarize_prospect_call",
            "ai_prompt_transcription_write_email_recap",
            "ai_voice_transcription",
            "selection__ai_composer__interface_key__voice_transcription_component",
        ],
        "ai",
        "ai_speech",
    )
