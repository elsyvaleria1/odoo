{
    "name": "Sale Subscription Tests",
    "version": "1.0",
    "category": "Sales/Subscriptions",
    "summary": "Test Sale Subscription behaviour, including subscription payment integration",
    "description": "Run regression tests for Sale Subscription. Loaded test suites include ``TestSubscriptionPaymentIntegration``.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/accounting",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_subscription",
        "payment_demo",
    ],
    "demo": [
        "demo/sale_subscription_demo.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "test_sale_subscription/static/tests/tours/*",
        ],
    },
}
