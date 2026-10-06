{
    "name": "Project Rental Orders",
    "category": "Sales/Sales",
    "summary": "Expose rental orders in project sales navigation",
    "description": "Extends project sales-order domains and actions and adds the associated rental sales view integration.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "sale_renting",
        "sale_project",
    ],
    "data": [
        "views/sale_order_views.xml",
    ],
    "auto_install": True,
}
