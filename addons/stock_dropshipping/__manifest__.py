{
    "name": "Dropshipping Routes",
    "version": "1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Route supplier deliveries directly to customers",
    "description": "Adds dropshipping routes and adapts procurement, purchase and stock-move handling for supplier-to-customer transfers.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_purchase_stock",
    ],
    "data": [
        "data/stock_data.xml",
        "views/sale_order_views.xml",
        "views/stock_picking_views.xml",
        "views/purchase_order_views.xml",
        "views/stock_dropshipping_menus.xml",
    ],
    "demo": [
        "demo/stock_dropshipping_demo.xml",
    ],
    "uninstall_hook": "uninstall_hook",
}
