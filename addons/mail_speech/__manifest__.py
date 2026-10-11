{
    "name": "Discuss Recording and Speech",
    "version": "19.0.1.2.0",
    "category": "Productivity/Discuss",
    "summary": "Record Discuss call segments, transcribe them and read messages aloud",
    "description": "Adds call recording controls, timed media uploads and call transcript displays, plus message read-aloud actions. Uploads require current call membership, an accepted audio or video type and a valid time span. Transcription is queued only when supported; transcription and synthesis require configured speech engines.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
        "speech",
    ],
    "data": [
        "views/discuss_call_history_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mail_speech/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "mail_speech/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
