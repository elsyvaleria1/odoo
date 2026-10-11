{
    "name": "POS DPO Pay Terminals",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Request and track POS payments through configured DPO terminals",
    "description": "Adds DPO payment-method settings and requests for transaction initiation, status, results and cancellation, with card or Mobile Money transaction modes. Requires a configured merchant account, terminal identifiers and service credentials. Accepted payment instruments and currencies depend on the provider and terminal setup.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "point_of_sale",
        "integration",
    ],
    "data": [
        "views/pos_payment_method_views.xml",
        "views/pos_payment_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_dpopay/static/src/**/*",
        ],
    },
}
