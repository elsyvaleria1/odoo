{
    "name": "Speech Processing Infrastructure",
    "version": "19.0.1.7.0",
    "oldest_upgradable_version": "19.0.1.6.0",
    "category": "Hidden",
    "sequence": 10,
    "summary": "Manage transcripts, speech-engine selection and live recording timelines",
    "description": "Adds attachment transcript state, timed cues, speaker records, vocabulary, subtitle routes and transcription actions. Extends media timelines with joined transcripts and provides live chunk and dictation infrastructure. Requires a separately installed and usable transcription or synthesis engine; this addon ships no engine and cannot transcribe every stored recording on its own.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "media",
        "bus",
    ],
    "data": [
        "security/ir.access.csv",
        "views/ir_attachment_views.xml",
        "views/media_segment_views.xml",
        "views/speech_vocabulary_views.xml",
        "views/speech_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "speech/static/src/**/*",
            (
                "remove",
                "speech/static/src/worklets/**/*",
            ),
        ],
        "web.assets_unit_tests": [
            "speech/static/tests/**/*",
        ],
    },
}
