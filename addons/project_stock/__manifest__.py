{
    "name": "Project Stock Transfers",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Link receipts and deliveries to projects",
    "description": "Adds a project field to stock transfers and project actions for receipts, deliveries and all related transfers.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock",
        "project",
    ],
    "data": [
        "views/stock_picking_views.xml",
        "views/project_project_views.xml",
    ],
    "auto_install": True,
}
