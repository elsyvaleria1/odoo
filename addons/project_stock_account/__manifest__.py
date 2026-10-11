{
    "name": "Project Inventory Costs",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Include stock-move analytic costs in project profitability",
    "description": "Adds analytic-cost configuration to operation types, prepares stock-move analytic entries and reports those costs on projects.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_account",
        "project_stock",
    ],
    "data": [
        "views/stock_picking_type_views.xml",
    ],
    "auto_install": True,
}
