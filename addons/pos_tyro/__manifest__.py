{
    "name": "POS Tyro Terminal Payments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "summary": "Process POS payments with configured Tyro terminals",
    "description": "Adds terminal pairing, merchant settings, receipt options and surcharge-product configuration to the Tyro POS payment interface. Requires a supported terminal and merchant account.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "point_of_sale",
    ],
    "data": [
        "data/pos_tyro_data.xml",
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "pos_tyro/static/src/urls.js",
            "pos_tyro/static/src/actions/**/*",
        ],
        "point_of_sale._assets_pos": [
            "pos_tyro/static/src/urls.js",
            "pos_tyro/static/src/app/**/*",
            "pos_tyro/static/src/overrides/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_tyro/static/tests/unit/data/**/*",
        ],
    },
}
