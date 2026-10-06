{
    "name": "Check Number Reconciliation",
    "version": "1.0",
    "category": "Accounting",
    "summary": "Display check numbers during bank reconciliation",
    "description": "Exposes payment check numbers on journal items and adds them to the reconciliation views.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account",
        "account_check_printing",
    ],
    "data": [
        "views/bank_rec_widget_views.xml",
    ],
    "auto_install": True,
}
