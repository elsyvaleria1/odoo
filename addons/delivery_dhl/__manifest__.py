{
    "name": "DHL Express Shipping Legacy",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Shipping Connectors",
    "sequence": 285,
    "summary": "Retain the legacy DHL Express shipping API integration",
    "description": "Contains the legacy DHL Express shipping client and carrier configuration. Use the replacement connector (delivery_dhl_rest) for the newer API; the legacy integration is marked unsupported.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_delivery",
        "mail",
    ],
    "data": [
        "data/delivery_dhl_data.xml",
        "views/delivery_dhl_view.xml",
    ],
    "demo": [
        "demo/demo.xml",
    ],
}
