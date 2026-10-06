{
    "name": "POS Mercado Pago Terminal Payments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Process POS payments with Mercado Pago terminals",
    "description": "Adds a Mercado Pago terminal payment method and the POS request and response handling for that integration. Requires a supported terminal and configured provider credentials or payment-provider account.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "point_of_sale",
        "integration",
    ],
    "data": [
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_mercado_pago/static/**/*",
        ],
    },
}
