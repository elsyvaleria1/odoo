{
    "name": "Website Modules Tests",
    "version": "1.0",
    "category": "Hidden",
    "sequence": 9876,
    "summary": "Test Website Modules behaviour, including configurator, controllers, performance",
    "description": "Run regression tests for Website Modules. Loaded test suites include ``TestConfigurator``, ``TestWebEditorController``, ``TestWebsiteAllPerformance``, ``TestWebsiteAllPerformanceShop``.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "theme_default",
        "website",
        "website_blog",
        "website_event_sale",
        "website_slides",
        "website_livechat",
        "website_crm_iap_reveal",
        "website_sale_comparison",
        "website_sale_wishlist",
    ],
    "assets": {
        "web.assets_tests": [
            "test_website_modules/static/tests/**/*",
        ],
    },
}
