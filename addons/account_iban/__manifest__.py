{
    "name": "IBAN Bank Accounts",
    "category": "Accounting/Accounting",
    "summary": "Validate and format IBAN bank account numbers",
    "description": "Recognize IBAN account numbers, validate their structure and extract their national bank-account components. Applies the checks when bank accounts are created or updated.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "account",
    ],
    "data": [
        "views/partner_view.xml",
        "wizards/wizard_res_partner_bank_account_create_views.xml",
    ],
    "demo": [
        "demo/res_partner_bank_account_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_iban/static/src/components/**/*",
        ],
        "web.assets_unit_tests": [
            "account_iban/static/tests/**/*",
        ],
    },
}
