{
    "name": "Postal Payment Follow-Ups",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Send payment follow-up documents through the postal-mail service",
    "description": "Adds postal delivery to follow-up configuration and generates the follow-up PDF for the mailing service. Requires service access, credits and a usable postal address.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "snailmail_account",
        "account_followup",
    ],
    "data": [
        "data/account_followup_data.xml",
        "views/account_followup_views.xml",
        "views/assets.xml",
        "wizards/wizard_res_partner_send_followup_views.xml",
    ],
    "demo": [
        "demo/account_followup_demo.xml",
    ],
    "assets": {
        "snailmail_account_followup.followup_report_assets_snailmail": [
            (
                "include",
                "web._assets_helpers",
            ),
            "web/static/src/scss/pre_variables.scss",
            "web/static/lib/bootstrap/scss/_variables.scss",
            "web/static/lib/bootstrap/scss/_variables-dark.scss",
            "web/static/lib/bootstrap/scss/_maps.scss",
        ],
    },
    "esm": {
        "bundles": [
            "snailmail_account_followup.followup_report_assets_snailmail",
        ],
    },
    "auto_install": True,
}
