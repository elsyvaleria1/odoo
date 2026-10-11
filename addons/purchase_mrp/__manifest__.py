{
    "name": "Manufacturing Purchase Links",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Supply Chain/Purchase",
    "summary": "Link purchased components and services to manufacturing orders",
    "description": "Expose related purchase and manufacturing orders from their respective forms. Carry manufacturing demand and stock-move information through purchase procurement.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mrp",
        "purchase_stock",
        "trade_mrp",
    ],
    "data": [
        "views/mrp_bom_views.xml",
        "views/purchase_order_views.xml",
        "views/mrp_production_views.xml",
        "views/stock_orderpoint_views.xml",
        "security/ir.access.csv",
    ],
    "demo": [
        "demo/purchase_mrp_demo.xml",
    ],
    "auto_install": True,
}
