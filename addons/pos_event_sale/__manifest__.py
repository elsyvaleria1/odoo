{
    "name": "POS and Sales Event Registration States",
    "category": "Hidden",
    "summary": "Reconcile event registration status across POS and sales orders",
    "description": "Extends registration-state calculation when both sales-order and POS ticket integrations are installed.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_event",
        "pos_sale",
    ],
    "auto_install": True,
}
