{
    "name": "Purchase Order Variant Grids",
    "version": "1.0",
    "category": "Supply Chain/Purchase",
    "summary": "Enter purchase quantities by product variant through a grid",
    "description": "Connects purchase orders to the shared order matrix mixin and adds grid controls and quotation or order report layouts. Requires configurable product variants; nonzero quantity changes are refused when a grid cell matches multiple purchase lines.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "purchase",
        "trade_product_matrix",
    ],
    "data": [
        "views/purchase_views.xml",
        "reports/purchase_quotation_templates.xml",
        "reports/purchase_order_templates.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "purchase_product_matrix/static/src/**/*",
        ],
        "web.assets_tests": [
            "purchase_product_matrix/static/tests/tours/**/*",
        ],
    },
}
