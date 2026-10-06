{
    "name": "Sales Manufacturing Links",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Sales",
    "summary": "Link sales demand to manufacturing orders and kit components",
    "description": "Expose the sales orders served by manufacturing and the production orders serving sales. Extend kit quantities and procurement handling in the sales flow.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mrp",
        "sale_stock",
        "trade_mrp",
    ],
    "data": [
        "security/ir.access.csv",
        "views/mrp_production_views.xml",
        "views/sale_order_views.xml",
        "views/sale_portal_templates.xml",
    ],
    "auto_install": True,
}
