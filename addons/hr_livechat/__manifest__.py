{
    "name": "Employee Live Chat Reporting",
    "version": "1.0",
    "category": "Human Resources",
    "summary": "Show employee information in live-chat conversation views",
    "description": "Extend live-chat channel, member-history and reporting views with employee information. Uses the existing HR and live-chat records.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr",
        "im_livechat",
    ],
    "data": [
        "views/discuss_channel_views.xml",
        "views/im_livechat_channel_member_history_views.xml",
        "views/im_livechat_report_channel_views.xml",
    ],
    "assets": {
        "im_livechat.embed_assets_unit_tests_setup": [
            (
                "remove",
                "hr/static/src/**/*",
            ),
            "hr/static/src/core/common/**/*",
        ],
    },
    "auto_install": True,
}
