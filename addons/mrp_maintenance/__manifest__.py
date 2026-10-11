{
    "name": "Manufacturing Maintenance Links",
    "version": "1.8",
    "oldest_upgradable_version": "1.7",
    "category": "Supply Chain/Manufacturing",
    "summary": "Create and open maintenance orders from manufacturing orders and work orders",
    "description": "Adds production and work-order references on maintenance orders and derives work-center links from their resources. Work-order actions prefill the production, company and work-center resource; maintenance scheduling and equipment history are supplied by the dependencies.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/maintenance",
    "license": "Other OSI approved licence",
    "depends": [
        "maintenance",
        "mrp_workorder",
        "resource_asset_mrp",
    ],
    "data": [
        "views/maintenance_views.xml",
        "views/mrp_views.xml",
        "views/mrp_maintenance_menus.xml",
    ],
    "demo": [
        "demo/mrp_maintenance_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mrp_maintenance/static/src/**/*.js",
            "mrp_maintenance/static/src/**/*.xml",
        ],
    },
    "auto_install": True,
}
