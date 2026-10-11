{
    "name": "Project Sales Deliveries",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Carry project references through sales-related stock transfers",
    "description": "Propagates project context into procurement and transfers and connects delivery actions to project sales lines.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_project",
        "sale_stock",
        "project_stock_account",
    ],
    "data": [
        "views/stock_move_views.xml",
    ],
    "auto_install": True,
}
