{
    "name": "Studio AI Field Configuration",
    "version": "0.1",
    "category": "Hidden",
    "summary": "Configure AI-computed fields in Studio",
    "description": "Adds AI field options and editor components to Studio. Field generation uses the configured AI service and the computation behavior supplied by the AI fields addon.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "ai_fields",
        "web_studio",
    ],
    "assets": {
        "web.assets_backend": [
            "web_studio_ai_fields/static/src/**/*.xml",
        ],
        "web_studio.studio_assets_minimal": [
            "web_studio_ai_fields/static/src/**/*.js",
            "web_studio_ai_fields/static/src/**/*.scss",
        ],
        "web.assets_unit_tests": [
            "web_studio_ai_fields/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
