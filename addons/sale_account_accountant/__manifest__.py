{
    "name": "Sales Accounting Reconciliation Links",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Identify related sales orders during accounting reconciliation",
    "description": "Adds reconciliation frontend components and sales-line views for the combined Sales and Accounting workflow.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale",
        "account",
    ],
    "data": [
        "views/sale_order_line_views.xml",
        "views/sale_account_accountant_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_account_accountant/static/src/components/**/*",
        ],
    },
    "auto_install": True,
}
