{
    "name": "Website Checkout Address Lookup",
    "version": "1.2",
    "oldest_upgradable_version": "1.1",
    "category": "Website/Website",
    "summary": "Suggest checkout addresses through the address autocomplete provider",
    "description": "Adds address lookup to the website sale checkout through the address provider chosen in the settings, called with each website's own key so visitors never spend the one internal users' lookups are made with. Without a provider or a website key, the checkout suggests nothing.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale",
        "address_autocomplete",
    ],
    "data": [
        "views/templates.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "address_autocomplete/static/src/address_session.js",
            "website_sale_autocomplete/static/src/interactions/address_form.js",
            "website_sale_autocomplete/static/src/xml/autocomplete.xml",
        ],
        "web.assets_tests": [
            "website_sale_autocomplete/static/tests/**/*.js",
        ],
    },
    "auto_install": True,
}
