{
    "name": "Asset Website Catalog and Quotes",
    "version": "19.0.1.0.0",
    "category": "Website/Website",
    "summary": "Display a vehicle catalog and WhatsApp quote links for configured products",
    "description": "Adds a vehicle catalog route, quote-only product settings and a per-website WhatsApp destination. Supplied templates replace the cart call to action for quote-only products with a quote link. Requires published catalog products and a configured destination; the module provides presentation and links rather than a WhatsApp messaging service.",
    "author": "AgroMarin",
    "website": "https://agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "asset_ledger",
        "website_sale",
    ],
    "data": [
        "data/product_public_category_data.xml",
        "views/product_template_views.xml",
        "views/res_config_settings_views.xml",
        "views/cta_templates.xml",
        "views/vehicles_catalog_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "asset_ledger_website_sale/static/src/js/vehicle_catalog.js",
        ],
        "web.assets_unit_tests_setup": [
            "asset_ledger_website_sale/static/src/js/vehicle_catalog.js",
        ],
        "web.assets_unit_tests": [
            "asset_ledger_website_sale/static/tests/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
}
