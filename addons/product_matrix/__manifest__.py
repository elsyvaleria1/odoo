{
    "name": "Product Variant Grid Components",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Build variant quantity grids and provide reusable matrix dialogs",
    "description": "Generates grid headers and cells from active product attribute values, marks possible combinations and optionally displays attribute price extras in the selected currency. Supplies shared dialog assets and report templates; sales or purchase grid extensions connect edits to order lines.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "data/res_groups.xml",
        "views/matrix_templates.xml",
    ],
    "demo": [
        "demo/product_matrix_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "product_matrix/static/src/js/matrix_configurator_hook.js",
            "product_matrix/static/src/js/product_matrix_dialog.js",
            "product_matrix/static/src/scss/product_matrix.scss",
            "product_matrix/static/src/xml/**/*",
        ],
    },
}
