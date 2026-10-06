{
    "name": "Helpdesk Live Chat Tickets",
    "category": "Services/Helpdesk",
    "sequence": 58,
    "summary": "Create and find helpdesk tickets from live chat conversations",
    "description": "Adds helpdesk chat commands, chatbot ticket-creation steps, conversation links and team live-chat configuration. Requires an enabled team integration and configured chat channel or chatbot flow; it does not provide an independent messaging service.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "website_helpdesk",
        "website_livechat",
    ],
    "data": [
        "data/helpdesk_livechat_chatbot_data.xml",
        "security/helpdesk_security.xml",
        "security/ir.access.csv",
        "views/chatbot_script_views.xml",
        "views/chatbot_script_step_views.xml",
        "views/discuss_channel_views.xml",
        "views/helpdesk_view.xml",
        "views/helpdesk_ticket_attachment_template.xml",
        "views/website_helpdesk_livechat_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "website_helpdesk_livechat/static/src/**/*",
        ],
        "mail.assets_public": [
            "website_helpdesk_livechat/static/src/core/common/**/*",
        ],
        "web.assets_unit_tests": [
            "website_helpdesk_livechat/static/tests/**/*",
            (
                "remove",
                "website_helpdesk_livechat/static/tests/tours/**/*",
            ),
        ],
        "web.assets_tests": [
            "website_helpdesk_livechat/static/tests/tours/**/*",
        ],
        "im_livechat.assets_livechat_support_tours": [
            "website_helpdesk_livechat/static/tests/tours/support/*",
        ],
        "im_livechat.embed_assets_unit_tests_setup": [
            (
                "remove",
                "website_helpdesk_livechat/static/src/core/web/**/*",
            ),
        ],
    },
    "auto_install": True,
    "post_init_hook": "_create_livechat_channel",
}
