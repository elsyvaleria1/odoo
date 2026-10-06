{
    "name": "Inventory Landed Costs",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Supply Chain/Inventory",
    "sequence": 16,
    "summary": "Allocate additional costs across eligible stock moves and update valuation",
    "description": "Adds landed-cost documents, split calculations and vendor-bill integration for transfer costs. Eligible moves require FIFO or average costing and a nonzero quantity. Validation checks balanced allocations, updates stock values and creates accounting entries for products with automated valuation; accounts and journals must be configured.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "purchase_stock",
    ],
    "data": [
        "security/ir.access.csv",
        "data/stock_landed_cost_data.xml",
        "views/account_move_views.xml",
        "views/product_views.xml",
        "views/stock_landed_cost_views.xml",
        "views/res_config_settings_views.xml",
        "views/stock_landed_costs_menus.xml",
    ],
}
