{
    "name": "Sales Order Variant Grids",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Enter sales quantities by product variant through a grid",
    "description": "Adds a product grid-entry mode, sales order interface and report grids through the shared order matrix mixin. Configurable products must use the matrix mode; combo lines are excluded, and ambiguous nonzero quantity changes across multiple matching lines are refused.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale",
        "trade_product_matrix",
    ],
    "data": [
        "views/product_template_views.xml",
        "views/sale_order_views.xml",
        "reports/sale_report_templates.xml",
    ],
    "demo": [
        "demo/product_matrix_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_product_matrix/static/src/**/*",
        ],
    },
}
