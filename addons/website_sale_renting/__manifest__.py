{
    "name": "eCommerce Rental",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Select rental dates and add rental products to online carts",
    "description": "Connects rental pricing and dates to eCommerce product pages, configurators and carts. Adds rental-period constraints and checkout validation using configured duration and day restrictions. Rental fulfillment uses the parent rental workflow and any installed stock integration.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale",
        "sale_renting",
    ],
    "data": [
        "security/ir.access.csv",
        "data/product_snippet_template_data.xml",
        "views/product_views.xml",
        "views/res_config_settings_views.xml",
        "views/templates.xml",
        "views/snippets/snippets.xml",
        "views/snippets/s_rental_search.xml",
    ],
    "demo": [
        "demo/demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "sale_renting/static/src/js/combo_configurator_dialog/*",
            "sale_renting/static/src/js/product_configurator_dialog/*",
            "website_sale_renting/static/src/interactions/**/*",
            "website_sale_renting/static/src/snippets/**/*.js",
            "website_sale_renting/static/src/scss/*.scss",
            (
                "before",
                "website_sale/static/src/interactions/website_sale.js",
                "website_sale_renting/static/src/js/*.js",
            ),
        ],
        "web.assets_tests": [
            "website_sale_renting/static/tests/tours/**/*",
        ],
        "website.website_builder_assets": [
            "website_sale_renting/static/src/plugins/**/*",
        ],
    },
    "auto_install": True,
}
