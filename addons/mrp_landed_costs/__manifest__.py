{
    "name": "Manufacturing Landed Costs",
    "version": "1.0",
    "category": "Supply Chain/Manufacturing",
    "summary": "Include selected manufacturing output moves in landed-cost allocation",
    "description": "Adds manufacturing order selection to landed costs and includes their finished stock moves among allocation targets. Byproduct moves without a cost share are excluded; allocation methods and valuation posting are supplied by Stock Landed Costs.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_landed_costs",
        "mrp",
    ],
    "data": [
        "views/stock_landed_cost_views.xml",
    ],
    "auto_install": True,
}
