{
    "name": "AI Voice Transcripts in the Editor",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Record a voice transcript in an HTML field and summarize it with an AI agent",
    "description": "Adds the editor's Voice Transcript block: it records through speech's live dictation, writes the transcript into the document as each chunk arrives and asks the AI agent of the voice-transcription composer rule for a summary, which the user can share in an email. Transcription requires a usable speech transcription engine; the summary requires the configured AI generation service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "ai",
        "speech",
    ],
    "data": [
        "data/ai_composer_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_speech/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "ai_speech/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
