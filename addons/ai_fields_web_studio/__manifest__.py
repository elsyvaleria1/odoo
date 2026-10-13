{
    "name": "Studio AI Field Configuration",
    "version": "0.1",
    "category": "Hidden",
    "summary": "Configure AI-computed fields in Studio",
    "description": "Adds AI field options and editor components to Studio. Field generation uses the configured AI service and the computation behavior supplied by the AI fields addon.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "ai_fields",
        "web_studio",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_fields_web_studio/static/src/**/*.xml",
        ],
        "web_studio.studio_assets_minimal": [
            "ai_fields_web_studio/static/src/**/*.js",
            "ai_fields_web_studio/static/src/**/*.scss",
        ],
        "web.assets_unit_tests": [
            "ai_fields_web_studio/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
