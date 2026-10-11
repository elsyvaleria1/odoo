{
    "name": "Payment Follow-Ups",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Accounting/Accounting",
    "summary": "Send payment reminders according to configured follow-up levels",
    "description": "Configure overdue-payment follow-up stages and their email, SMS or letter actions. Generate reminders and track the next follow-up date for the selected customers.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/invoicing",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
        "sms",
        "account",
    ],
    "data": [
        "security/ir.access.csv",
        "data/mail_template.xml",
        "data/account_followup_data.xml",
        "data/cron.xml",
        "wizards/wizard_res_partner_send_followup_views.xml",
        "wizards/followup_missing_information.xml",
        "views/account_followup_views.xml",
        "views/account_followup_line_views.xml",
        "views/account_move_views.xml",
        "views/partner_view.xml",
        "views/report_followup.xml",
        "views/account_followup_menus.xml",
    ],
    "demo": [
        "demo/account_followup_demo.xml",
    ],
    "assets": {
        "account_followup.assets_followup_report": [
            (
                "include",
                "web._assets_helpers",
            ),
            "web/static/src/scss/pre_variables.scss",
            "web/static/lib/bootstrap/scss/_variables.scss",
            "web/static/lib/bootstrap/scss/_variables-dark.scss",
            "web/static/lib/bootstrap/scss/_maps.scss",
            (
                "include",
                "web._assets_bootstrap_backend",
            ),
            "web/static/fonts/fonts.scss",
        ],
        "web.assets_backend": [
            "account_followup/static/src/components/**/*.js",
        ],
    },
    "esm": {
        "bundles": [
            "account_followup.assets_followup_report",
        ],
    },
    "auto_install": True,
}
