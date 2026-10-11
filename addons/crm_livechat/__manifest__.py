{
    "name": "Live Chat Lead Creation",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/CRM",
    "summary": "Create CRM leads from live chat commands and configured chatbot steps",
    "description": "Adds the /lead command, chatbot lead-creation steps and links between CRM leads and chat conversations. Command-created leads include conversation history and available visitor contact information; chatbot lead creation requires the corresponding configured steps.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "crm",
        "im_livechat",
    ],
    "data": [
        "data/utm_data.xml",
        "data/crm_livechat_chatbot_data.xml",
        "views/chatbot_script_views.xml",
        "views/chatbot_script_step_views.xml",
        "views/crm_lead_views.xml",
        "views/discuss_channel_views.xml",
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "crm_livechat/static/src/core/**/*",
        ],
        "web.assets_unit_tests": [
            "crm_livechat/static/tests/**/*",
            (
                "remove",
                "crm_livechat/static/tests/tours/**/*",
            ),
        ],
        "im_livechat.assets_livechat_support_tours": [
            "crm_livechat/static/tests/tours/support/*",
        ],
        "im_livechat.embed_assets_unit_tests_setup": [
            (
                "remove",
                "crm_livechat/static/src/core/web/**/*",
            ),
        ],
    },
    "auto_install": True,
}
