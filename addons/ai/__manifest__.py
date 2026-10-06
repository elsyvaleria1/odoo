{
    "name": "AI Agent Foundation",
    "version": "1.3",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden",
    "summary": "Provide AI agents, source indexing and model-provider connections",
    "description": "Supply AI agent and topic models, document-source indexing, chat responses and AI tools backed by configured model providers. Provider credentials and agent configuration determine which services and sources are available.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "credential",
        "mail",
        "speech",
    ],
    "data": [
        "data/ir_actions_server_data.xml",
        "data/ai_topic_data.xml",
        "security/ai_answer_privilege.xml",
        "security/ir.access.csv",
        "views/res_config_settings_views.xml",
        "views/ir_actions_server_views.xml",
        "views/mail_scheduled_message_views.xml",
        "views/mail_template_views.xml",
        "views/templates.xml",
        "data/ir_cron.xml",
        "data/ai_agent_data.xml",
        "data/ai_composer_data.xml",
        "wizards/wizard_mail_message_send_views.xml",
    ],
    "demo": [
        "demo/ai_agent_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            (
                "after",
                "web/static/src/views/form/form_controller.js",
                "ai/static/src/web/form_controller_patch.js",
            ),
            "ai/static/src/**/*",
        ],
        "mail.assets_public": [
            "ai/static/src/discuss/core/common/**/*",
        ],
        "portal.assets_chatter_helpers": [
            "ai/static/src/discuss/core/common/**/*",
            (
                "remove",
                "ai/static/src/discuss/core/common/thread_model_patch.js",
            ),
        ],
        "im_livechat.assets_embed_core": [
            "ai/static/src/discuss/core/common/**/*",
        ],
        "web.assets_unit_tests": [
            "ai/static/tests/**/*",
        ],
    },
    "pre_init_hook": "_pre_init_ai",
}
