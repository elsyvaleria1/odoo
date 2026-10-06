{
    "name": "External Invoice Tax Calculation",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Delegate invoice tax calculation to configured external services",
    "description": "Provide the invoice tax-calculation interface used by external tax connectors. Handles calculation, commitment and cancellation hooks; provider modules implement the service calls.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account",
        "payment",
    ],
    "data": [
        "views/account_move_views.xml",
    ],
}
