{
    "name": "Sale Product Configurators Tests",
    "category": "Hidden",
    "summary": "Test Sale Product Configurators behaviour, including event sale with product configurator, sale product matrix, sale product configurator",
    "description": "Run regression tests for Sale Product Configurators. Loaded test suites include ``TestEventProductConfiguratorUi``, ``TestSaleMatrixUi``, ``TestProductConfiguratorUi``.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "event_sale",
        "sale",
        "sale_product_matrix",
    ],
    "assets": {
        "web.assets_tests": [
            "test_sale_product_configurators/static/tests/tours/**/*",
        ],
    },
}
