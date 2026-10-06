{
    "name": "POS Repair Order Sales",
    "category": "Hidden",
    "summary": "Handle repair-related sales lines in the POS",
    "description": "Marks repair sale lines in POS data and adapts stock-transfer creation for those lines.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "repair",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_repair/static/src/**/*",
        ],
        "web.assets_tests": [
            "pos_repair/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
