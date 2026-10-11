{
    "name": "Contacts",
    "category": "Sales/CRM",
    "sequence": 150,
    "summary": "Browse contacts and maintain birth dates and age ranges",
    "description": "Adds the Contacts application menu and directory views over shared contact records. Extends contacts with birth dates, calculated ages and configurable age ranges. Customer and supplier workflows are supplied by their respective business applications.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
    ],
    "data": [
        "security/ir.access.csv",
        "views/res_partner_age_range_views.xml",
        "views/res_partner_views.xml",
        "views/ir_ui_menu_views.xml",
    ],
    "demo": [
        "demo/res_partner_age_range_demo.xml",
        "demo/mail_demo.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "partner/static/tests/tours/**/*",
        ],
    },
    "application": True,
}
