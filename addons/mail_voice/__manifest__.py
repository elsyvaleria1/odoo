{
    "name": "Voice Chatter Composition",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Draft chatter notes and messages from recognized voice commands",
    "description": "Adds voice executors that open the note or message composer on a saved record and append recognized text. Requires an available chatter and voice recognition; the user reviews and sends the draft, while undo restores the previous composer text.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
        "voice",
    ],
    "assets": {
        "web.assets_backend": [
            "mail_voice/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "mail_voice/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
