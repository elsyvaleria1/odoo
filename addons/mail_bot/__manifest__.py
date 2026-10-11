{
    "name": "Messaging Assistant Bot",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Productivity/Discuss",
    "summary": "Guide users through messaging features with automated bot replies",
    "description": "Adds the onboarding bot and its scripted responses to supported messaging interactions.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/discuss",
    "license": "Other OSI approved licence",
    "depends": [
        "mail",
    ],
    "data": [
        "views/res_users_views.xml",
        "data/mailbot_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mail_bot/static/src/scss/odoobot_style.scss",
        ],
    },
    "auto_install": True,
}
