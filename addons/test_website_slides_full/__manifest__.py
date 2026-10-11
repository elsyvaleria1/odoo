{
    "name": "eLearning Integration Tests",
    "version": "1.0",
    "category": "Hidden/Tests",
    "summary": "Test eLearning Integration behaviour, including ui wslides",
    "description": "Run regression tests for eLearning Integration. Loaded test suites include ``TestUi``.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale_slides",
        "website_slides_forum",
        "website_slides_survey",
    ],
    "data": [
        "data/res_groups_data.xml",
    ],
    "demo": [
        "demo/product_demo.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "test_website_slides_full/static/tests/tours/**/*",
        ],
    },
}
