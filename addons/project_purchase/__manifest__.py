{
    "name": "Project Purchase Orders",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Link purchase orders and purchase costs to projects",
    "description": "Adds project references to purchase orders, propagates analytic distribution to lines and supplies purchase navigation and profitability entries.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "purchase",
        "project_account",
    ],
    "data": [
        "views/project_project.xml",
        "views/purchase_order.xml",
    ],
    "demo": [
        "demo/project_purchase_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "project_purchase/static/src/product_catalog/kanban_record.js",
        ],
    },
    "auto_install": True,
}
