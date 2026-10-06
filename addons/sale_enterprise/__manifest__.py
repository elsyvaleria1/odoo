{
    "name": "Sales Order Map",
    "category": "Sales/Sales",
    "summary": "Display sales orders on a map",
    "description": "Adds a map view to the sales-order action using the geographic data of the related customer.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sale",
        "web_map",
    ],
    "data": [
        "views/sale_order_views.xml",
    ],
    "auto_install": True,
}
