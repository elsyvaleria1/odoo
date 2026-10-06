{
    "name": "Subscription Stock Deliveries",
    "version": "1.0",
    "category": "Sales/Subscriptions",
    "summary": "Manage recurring stock delivery quantities by subscription billing period",
    "description": "Adapts stock procurement, delivered quantities, returns and forecast reporting for recurring stock subscription lines. Post-invoice processing closes the invoiced delivery period and can launch procurement for the next period; stock routes and subscription configuration determine the resulting moves.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/subscriptions",
    "license": "OEEL-1",
    "depends": [
        "sale_subscription",
        "sale_stock",
    ],
    "data": [
        "views/product_template_views.xml",
        "views/sale_order_views.xml",
        "data/sale_subscription_stock_data.xml",
    ],
    "demo": [
        "demo/sale_subscription_stock_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_subscription_stock/static/src/*",
        ],
    },
    "auto_install": True,
}
