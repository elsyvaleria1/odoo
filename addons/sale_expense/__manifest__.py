{
    "name": "Sales Expense Reinvoicing",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Link employee expenses to sales orders for customer reinvoicing",
    "description": "Adds sales order selection on eligible expenses and creates reinvoice sales lines from expense accounting entries. Product expense policies and the linked sales order determine reinvoicing; expense approval and customer invoice posting remain in their respective workflows.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "sale",
        "hr_expense",
    ],
    "data": [
        "data/sale_expense_data.xml",
        "views/product_view.xml",
        "views/hr_expense_views.xml",
        "views/sale_order_views.xml",
    ],
    "auto_install": True,
}
