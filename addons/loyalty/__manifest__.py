{
    "name": "Loyalty Programs",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Sales/Sales",
    "summary": "Configure reward programs, coupons and loyalty cards",
    "description": "Defines program rules, rewards, points and coupon cards with validity conditions. Sales-channel addons apply these programs to their orders.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.access.csv",
        "reports/loyalty_report_templates.xml",
        "reports/loyalty_report.xml",
        "data/mail_template_data.xml",
        "data/loyalty_data.xml",
        "wizards/wizard_loyalty_card_update_balance_views.xml",
        "wizards/wizard_loyalty_program_create_card_views.xml",
        "views/loyalty_card_views.xml",
        "views/loyalty_history_views.xml",
        "views/loyalty_mail_views.xml",
        "views/loyalty_program_views.xml",
        "views/loyalty_reward_views.xml",
        "views/loyalty_rule_views.xml",
        "views/portal_templates.xml",
        "views/res_partner_views.xml",
    ],
    "demo": [
        "demo/loyalty_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "loyalty/static/src/js/**/*.js",
            "loyalty/static/src/scss/*.scss",
            "loyalty/static/src/xml/*.xml",
            (
                "remove",
                "loyalty/static/src/js/portal/**/*",
            ),
        ],
        "web.assets_web_dark": [],
        "web.assets_unit_tests": [
            "loyalty/static/tests/unit/**/*",
        ],
        "web.assets_frontend": [
            "loyalty/static/src/js/portal/**/*",
            "loyalty/static/src/interactions/*",
        ],
    },
}
