{
    "name": "eCommerce Course Sales",
    "version": "1.0",
    "category": "Website/eLearning",
    "summary": "Sell course products and enroll customers when sales orders are confirmed",
    "description": "Connects paid-enrollment courses to products, website purchase controls and sales reporting. Order confirmation adds the order contact to matching courses; course products are limited to one unit in the cart. Checkout and payment processing come from eCommerce, and enrollment follows order confirmation rather than a separate payment check here.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "website_slides",
        "website_sale",
    ],
    "data": [
        "data/product_data.xml",
        "reports/sale_report_views.xml",
        "views/website_slides_menu_views.xml",
        "views/product_template_views.xml",
        "views/slide_channel_views.xml",
        "views/website_sale_templates.xml",
        "views/website_slides_templates.xml",
    ],
    "demo": [
        "demo/product_demo.xml",
        "demo/slide_demo.xml",
        "demo/sale_order_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_slides/static/src/js/**/*",
            "website_sale_slides/static/src/xml/**/*",
        ],
        "web.assets_tests": [
            "website_sale_slides/static/tests/tours/*.js",
        ],
        "website.website_builder_assets": [
            "website_sale_slides/static/src/website_builder/**/*",
        ],
    },
}
