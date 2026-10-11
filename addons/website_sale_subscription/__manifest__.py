{
    "name": "eCommerce Subscription Sales",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Offer recurring plans and subscription pricing in the website cart",
    "description": "Adds recurring price displays, plan selection and subscription cart handling. Products need applicable recurring pricing; the cart rejects conflicting subscription plans and requires a customer address for a plan. Recurring invoices and subscription lifecycle actions come from the subscription dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale",
        "sale_subscription",
    ],
    "data": [
        "views/templates.xml",
        "views/sale_order_views.xml",
    ],
    "demo": [
        "demo/demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "sale_subscription/static/src/js/combo_configurator_dialog/*",
            "sale_subscription/static/src/js/product_configurator_dialog/*",
            (
                "before",
                "website_sale/static/src/interactions/website_sale.js",
                "website_sale_subscription/static/src/js/variant_mixin.js",
            ),
            "website_sale_subscription/static/src/js/combo_configurator_dialog/*",
            "website_sale_subscription/static/src/js/product_configurator_dialog/*",
            "website_sale_subscription/static/src/interactions/*",
            "website_sale_subscription/static/src/xml/pricing_view.xml",
        ],
        "web.assets_tests": [
            "website_sale_subscription/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
