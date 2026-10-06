{
    "name": "Website Checkout Address Lookup",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Website/Website",
    "summary": "Suggest checkout addresses through Google Places",
    "description": "Adds address lookup to the website sale checkout using a configured Google Places API key. Suggestions depend on the provider response and require its service access.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website_sale",
        "google_address_autocomplete",
    ],
    "data": [
        "views/templates.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "google_address_autocomplete/static/src/google_places_session.js",
            "website_sale_autocomplete/static/src/interactions/address_form.js",
            "website_sale_autocomplete/static/src/xml/autocomplete.xml",
        ],
        "web.assets_tests": [
            "website_sale_autocomplete/static/tests/**/*.js",
        ],
    },
    "auto_install": True,
}
