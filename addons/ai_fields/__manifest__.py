{
    "name": "AI Field Computation",
    "version": "0.1",
    "category": "Hidden",
    "summary": "Fill configured fields and properties using AI prompts",
    "description": "Adds prompt and record-domain settings for AI-computed fields and scheduled filling of eligible empty values. Requires a configured AI provider; generated values depend on the prompt and source records.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "ai",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "views/ir_model_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_fields/static/src/model/**/*",
            "ai_fields/static/src/views/**/*",
        ],
        "web.assets_unit_tests": [
            "ai_fields/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
