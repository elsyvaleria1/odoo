{
    "name": "Subcontracting Purchase Links",
    "version": "0.1",
    "category": "Supply Chain/Purchase",
    "summary": "Link purchase orders to subcontracted production and resupply transfers",
    "description": "Expose subcontracting resupply and production records from purchase orders. Extend procurement and return handling for the subcontracting purchase flow.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mrp_subcontracting",
        "purchase_mrp",
    ],
    "data": [
        "views/purchase_order_views.xml",
        "views/stock_picking_views.xml",
    ],
    "demo": [
        "demo/mrp_subcontracting_purchase_demo.xml",
    ],
    "auto_install": True,
}
