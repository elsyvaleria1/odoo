{
    "name": "Project Purchase Transfers",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Copy project links from purchases to generated stock transfers",
    "description": "Carry a purchase order's project into picking values and project-related purchase selection. Keeps purchase and inventory records associated with the project.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "project_purchase",
        "project_stock",
        "purchase_stock",
    ],
    "auto_install": True,
}
