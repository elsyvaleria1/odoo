{
    "name": "UPS Shipping Legacy",
    "version": "1.0",
    "category": "Shipping Connectors",
    "sequence": 275,
    "summary": "Retain the legacy UPS shipping API integration",
    "description": "Contains the legacy UPS shipping client and carrier configuration. Use the replacement connector (delivery_ups_rest) for the newer API; the legacy integration is marked unsupported.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_delivery",
        "mail",
    ],
    "data": [
        "data/delivery_ups_data.xml",
        "views/delivery_ups_view.xml",
        "views/sale_order_views.xml",
        "views/res_partner_views.xml",
    ],
}
