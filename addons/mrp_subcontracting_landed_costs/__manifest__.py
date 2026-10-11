{
    "name": "Subcontracting Landed Cost Selection",
    "version": "1.0",
    "category": "Supply Chain/Manufacturing",
    "summary": "Select subcontracting production and transfers for landed costs",
    "description": "Adapts the landed-cost form with subcontracting production search views and eligible completed subcontracting transfers.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_landed_costs",
        "mrp_subcontracting",
    ],
    "data": [
        "views/stock_landed_cost_views.xml",
    ],
    "auto_install": True,
}
