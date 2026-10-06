{
    "name": "Google Address Autocomplete",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden/Tools",
    "summary": "Suggest and complete addresses using configured Google Places access",
    "description": "Adds address widgets and server routes for Google place suggestions and structured address details. The base integration requires an internal user and a configured Google Places API key in the credential store; requests depend on provider access and availability.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "credential",
        "web",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
        "views/res_company_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "google_address_autocomplete/static/src/**/*",
        ],
        "web._assets_core": [
            "google_address_autocomplete/static/src/address_autocomplete/google_address_autocomplete.scss",
        ],
        "web.assets_tests": [
            "google_address_autocomplete/static/tests/tours/*.js",
        ],
        "web.assets_unit_tests": [
            "google_address_autocomplete/static/tests/**/*.test.js",
        ],
    },
}
