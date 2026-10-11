{
    "name": "Purchase Accrual Views",
    "version": "1.0",
    "category": "Supply Chain/Purchase",
    "summary": "Review purchase lines using accrual and closing filters",
    "description": "Adds purchase-line views, filters and actions for accounting closing and accrual review.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "purchase",
        "account",
    ],
    "data": [
        "views/purchase_order_line_views.xml",
        "views/purchase_accountant_menus.xml",
    ],
    "auto_install": True,
}
