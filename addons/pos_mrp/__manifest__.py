{
    "name": "POS Manufacturing Cost Calculation",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Calculate POS product costs through related manufacturing moves",
    "description": "Extends POS stock-move selection and Anglo-Saxon unit-cost calculation for manufactured products.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "point_of_sale",
        "mrp",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_tests": [
            "pos_mrp/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
