{
    "name": "AI Agent Management",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Configure AI agents, topics and composer rules through the backend",
    "description": "Add management views and menus for agents, topics and AI composer rules supplied by the AI foundation module. The underlying providers and document-source processing come from its dependencies.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "attachment_indexation",
        "ai",
    ],
    "data": [
        "views/ai_agent_views.xml",
        "views/ai_topic_views.xml",
        "views/ai_composer_views.xml",
        "views/res_config_settings_views.xml",
        "views/ai_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "ai_app/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "ai_app/static/tests/**/*",
        ],
    },
    "application": True,
}
