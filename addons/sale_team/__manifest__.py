{
    "name": "Sales Teams",
    "version": "2.2",
    "oldest_upgradable_version": "2.2",
    "category": "Sales/Sales",
    "summary": "Assign sales documents to teams and report team invoice targets",
    "description": "Extends shared teams with sales usage, invoice targets, dashboard actions and sales-order links. Adds team fields to orders, accounting documents, users and sales reports. Requires the Sales and Teams dependencies; CRM-specific functionality is supplied by its own integration.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/crm",
    "license": "Other OSI approved licence",
    "depends": [
        "sale",
        "team",
    ],
    "data": [
        "security/ir.access.csv",
        "data/team_team_data.xml",
        "data/mail_message_subtype_data.xml",
        "reports/account_invoice_report_views.xml",
        "reports/sale_report_views.xml",
        "views/account_move_views.xml",
        "views/crm_tag_views.xml",
        "views/sale_order_views.xml",
        "views/team_team_views.xml",
        "views/mail_activity_views.xml",
        "views/res_config_settings_views.xml",
        "views/sale_team_menus.xml",
    ],
    "demo": [
        "demo/team_team_demo.xml",
        "demo/crm_tag_demo.xml",
        "demo/sale_order_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_team/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "sale_team/static/tests/**/*.test.js",
        ],
    },
    "auto_install": [
        "sale",
    ],
}
