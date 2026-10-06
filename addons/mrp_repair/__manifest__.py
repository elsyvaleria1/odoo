{
    "name": "Manufacturing Repair Links",
    "version": "1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Link repair orders with related manufacturing orders",
    "description": "Expose manufacturing and repair links and support kit component expansion in repairs. Adds navigation between the related production and repair records.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "repair",
        "mrp",
    ],
    "data": [
        "views/production_views.xml",
        "views/repair_views.xml",
    ],
    "auto_install": True,
}
