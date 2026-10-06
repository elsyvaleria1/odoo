{
    "name": "Sales Procurement Purchase Links",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Link sales and purchase orders through stock procurement references",
    "description": "Extends order navigation, procurement line links, destination-address handling and stock-move preparation across sales and purchasing. Uses stock references and configured procurement routes, including make-to-order and dropship flows; procurement creation and route execution come from the dependencies.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "sale_stock",
        "purchase_stock",
        "sale_purchase",
    ],
    "data": [
        "views/purchase_order_views.xml",
    ],
    "auto_install": True,
}
