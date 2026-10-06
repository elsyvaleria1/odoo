{
    "name": "POS Subscription Payments",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "sequence": 15,
    "summary": "Update subscription sales when linked POS orders are paid",
    "description": "Extends paid POS order processing and subscription invoiced-quantity calculation for linked sales lines.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "pos_sale",
        "sale_subscription",
    ],
    "auto_install": True,
}
