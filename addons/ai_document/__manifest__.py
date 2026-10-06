{
    "name": "AI Document Sorting",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden",
    "summary": "Run configured AI sorting actions on eligible documents",
    "description": "Adds folder sorting prompts, automation rules, document move and tag tools, and manual or scheduled sorting. Requires configured folder instructions and an available AI model through the AI dependency. Only eligible documents with applicable sorting configuration are processed.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "ai",
        "document",
        "automation",
    ],
    "data": [
        "data/ir_actions_server_tools.xml",
        "data/ir_cron.xml",
        "views/document_document_views.xml",
        "security/ir.access.csv",
        "wizards/wizard_document_document_setup_ai_sort_views.xml",
    ],
    "demo": [
        "demo/ir_actions_server_tools.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_document/static/src/cog_menu/*",
            "ai_document/static/src/scss/*",
            "ai_document/static/src/views/**/*",
            "ai_document/static/src/views/*",
            "ai_document/static/src/*",
        ],
        "web.assets_unit_tests": [
            "ai_document/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
