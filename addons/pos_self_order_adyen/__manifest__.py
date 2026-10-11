{
    "name": "Self-Order Adyen Payments",
    "category": "Sales/Point of Sale",
    "summary": "Process kiosk payments through Adyen",
    "description": "Connects the self-order payment flow to the Adyen POS integration and its payment-status handling. Requires that integration and a configured supported terminal.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_adyen",
        "pos_self_order",
    ],
    "auto_install": True,
}
