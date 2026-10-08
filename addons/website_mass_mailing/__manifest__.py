{
    "name": "Website Mailing Subscriptions",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Add website forms and snippets for mailing-list subscriptions",
    "description": "Adds newsletter subscription interfaces and routes that create mailing contacts or restore opted-out list subscriptions. Requires a configured mailing list and website form or snippet; the subscription route applies the configured reCAPTCHA check. Message delivery is supplied by the mailing dependencies.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website",
        "mass_mailing",
        "captcha",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_model_data.xml",
        "views/snippets_templates.xml",
        "views/snippets/s_newsletter_benefits_popup.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_mass_mailing/static/src/scss/website_mass_mailing.scss",
            "website_mass_mailing/static/src/interactions/**/*",
            "website_mass_mailing/static/src/scss/website_mass_mailing_popup.scss",
            "website_mass_mailing/static/src/interactions/fix_newsletter_list_class.edit.js",
            "website_mass_mailing/static/src/xml/*.xml",
        ],
        "website.assets_wysiwyg": [
            "website_mass_mailing/static/src/scss/website_mass_mailing_edit_mode.scss",
        ],
        "website.website_builder_assets": [
            "website_mass_mailing/static/src/js/mass_mailing_form_editor.js",
            "website_mass_mailing/static/src/plugins/form_option_plugin.js",
            "website_mass_mailing/static/src/website_builder/**/*",
            (
                "remove",
                "website_mass_mailing/static/src/website_builder/**/*.edit.*",
            ),
        ],
        "website.assets_inside_builder_iframe": [
            "website_mass_mailing/static/src/website_builder/mailing_list_subscribe_option.edit.*",
        ],
        "web.assets_tests": [
            "website_mass_mailing/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "website_mass_mailing/static/tests/interactions/**/*",
        ],
        "web.assets_unit_tests_setup": [
            "website_mass_mailing/static/src/interactions/**/*",
        ],
    },
    "auto_install": [
        "website",
        "mass_mailing",
    ],
}
