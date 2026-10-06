{
    "name": "IAP Account Notifications",
    "version": "1.0",
    "category": "Hidden/Tools",
    "summary": "Notify configured users about IAP account status and low credits",
    "description": "Adds warning thresholds and recipients to IAP accounts, with email templates for status, errors and exhausted credits.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "iap",
        "mail",
    ],
    "data": [
        "data/mail_templates.xml",
        "views/iap_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "iap_mail/static/src/js/**/*",
            "iap_mail/static/src/scss/iap_mail.scss",
        ],
    },
    "auto_install": True,
}
