{
    "name": "Web Client Voice Commands",
    "version": "19.0.1.3.0",
    "oldest_upgradable_version": "19.0.1.3.0",
    "category": "Hidden",
    "summary": "Interpret spoken or typed commands for navigation, search and form actions",
    "description": "Adds command interpretation, voice UI controls, screen integration hooks, form-field dictation and spoken feedback through browser synthesis. A command is heard by the browser's recogniser or, through speech, by a server engine the company's policy allows, without keeping the audio. Supported changes or confirmations are staged in the current interface. Requires browser permissions and an available engine; command coverage depends on the active screen, language and registered handlers.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "speech",
    ],
    "data": [
        "security/voice_security.xml",
        "security/ir.access.csv",
        "security/ir_access.xml",
        "data/speech_vocabulary_form_data.xml",
        "views/voice_sentence_views.xml",
        "views/speech_vocabulary_form_views.xml",
        "views/voice_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "voice_command/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "voice_command/static/tests/**/*",
        ],
    },
}
