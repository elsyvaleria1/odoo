{
    "name": "Website SMS Newsletter Subscription",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Collect phone-number subscriptions through an SMS newsletter block",
    "description": "Adds a phone-number variant of the website newsletter block and adapts subscription handling to its phone field. Requires a configured mailing list and the SMS mailing dependency; adding a subscriber does not itself send a campaign.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website_mass_mailing",
        "mass_mailing_sms",
    ],
    "data": [
        "views/snippets/snippets_templates.xml",
        "data/ir_model_data.xml",
    ],
    "assets": {
        "website.website_builder_assets": [
            "website_mass_mailing_sms/static/src/website_builder/**/*",
        ],
    },
    "auto_install": True,
}
