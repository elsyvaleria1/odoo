{
    "name": "Subcontractor Dropshipping",
    "version": "0.2",
    "oldest_upgradable_version": "0.2",
    "category": "Supply Chain/Purchase",
    "summary": "Route purchased components directly to subcontractors",
    "description": "Provide subcontractor dropshipping configuration, routes and stock-flow handling. Link dropshipped component moves to subcontracted manufacturing orders.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mrp_subcontracting",
        "stock_dropshipping",
    ],
    "data": [
        "security/ir.access.csv",
        "data/mrp_subcontracting_dropshipping_data.xml",
        "views/purchase_order_views.xml",
    ],
    "auto_install": True,
}
