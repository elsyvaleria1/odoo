{
    "name": "POS Python-Defined Taxes",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Load custom tax computation data in Point of Sale",
    "description": "Extend the tax fields loaded into the POS and its tax computation assets. Uses the custom tax definitions from the Python-tax dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "tax_python",
        "point_of_sale",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "tax_python/static/src/helpers/*.js",
        ],
        "web.assets_unit_tests": [
            "pos_tax_python/static/tests/unit/data/**/*",
        ],
        "web.assets_tests": [
            "pos_tax_python/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
