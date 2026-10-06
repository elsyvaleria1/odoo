{
    "name": "Employee Voiceprint Matching",
    "version": "19.0.1.0.0",
    "category": "Human Resources/Employees",
    "summary": "Match transcript speakers against enrolled employee voiceprints",
    "description": "Adds employee enrollment and revocation endpoints, stored speaker embeddings and threshold-based matching on transcript speakers. Requires the local decoding and inference libraries and a configured model file. Enrollment records consent and matching can leave speakers unidentified; it is not guaranteed identity verification.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "speech",
    ],
    "external_dependencies": {
        "python": [
            "numpy",
        ],
    },
    "data": [
        "security/ir.access.csv",
        "data/ir_config_parameter.xml",
        "views/speech_voiceprint_views.xml",
        "views/ir_attachment_views.xml",
        "views/speech_voiceprint_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "speech_voiceprint/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "speech_voiceprint/static/tests/**/*",
        ],
    },
}
