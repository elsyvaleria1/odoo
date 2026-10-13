{
    "name": "AI Voice Intent Interpretation",
    "version": "19.0.1.0.0",
    "category": "Hidden",
    "summary": "Interpret unmatched voice commands using configured language models",
    "description": "Adds a voice-command fallback that sends the sentence and offered action choices through the machine-learning gateway under the voice.intent purpose. Requires an eligible configured model and policy. Returned action IDs are filtered against the offered choices and passed to the voice proposal workflow; this addon does not itself execute arbitrary model instructions.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "integration_machine_learning",
        "voice_command",
    ],
    "data": [
        "data/integration_ml_purpose_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "voice_command_ml/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "voice_command_ml/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
