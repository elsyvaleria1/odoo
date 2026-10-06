{
    "name": "FedEx Shipping Legacy",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Shipping Connectors",
    "sequence": 295,
    "summary": "Retain the legacy FedEx shipping API integration",
    "description": "Contains the legacy FedEx shipping client and carrier configuration. Use the replacement connector (delivery_fedex_rest) for the newer API; the legacy integration is marked unsupported.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_delivery",
        "mail",
    ],
    "data": [
        "data/delivery_fedex.xml",
        "views/delivery_fedex.xml",
    ],
}
