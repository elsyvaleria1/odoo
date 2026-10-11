{
    "name": "Address Autocomplete",
    "version": "1.0",
    "category": "Hidden/Tools",
    "summary": "Suggest and complete addresses through the provider chosen in the settings",
    "description": "Adds the address autocomplete field widget, set on the street of partner and company forms, and the server routes answering its suggestions and the chosen address's details. Lookups go to the installed provider chosen in the settings, with the key that provider keeps for internal users; without a provider the widget suggests nothing.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "data": [
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "address_autocomplete/static/src/**/*",
        ],
        "web._assets_core": [
            "address_autocomplete/static/src/address_autocomplete/address_autocomplete.scss",
        ],
        "web.assets_tests": [
            "address_autocomplete/static/tests/tours/*.js",
        ],
        "web.assets_unit_tests": [
            "address_autocomplete/static/tests/**/*.test.js",
        ],
    },
}
