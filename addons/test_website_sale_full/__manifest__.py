{
    "name": "Website Sale Full Tests",
    "category": "Hidden",
    "summary": "Test Website Sale Full behaviour, including ui rental comparison, ui rental wishlist",
    "description": "Run regression tests for Website Sale Full. Loaded test suites include ``TestUi``.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale_comparison",
        "website_sale_renting",
        "website_sale_wishlist",
    ],
    "assets": {
        "web.assets_tests": [
            "test_website_sale_full/static/tests/tours/**/*",
        ],
    },
}
