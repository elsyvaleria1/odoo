{
    "name": "USPS Shipping Legacy",
    "version": "1.0",
    "category": "Shipping Connectors",
    "sequence": 305,
    "summary": "Retain the legacy USPS shipping API integration",
    "description": "Contains the legacy USPS shipping client and carrier configuration. Use the replacement connector (delivery_usps_rest) for the newer API; the legacy integration is marked unsupported.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_delivery",
        "mail",
    ],
    "data": [
        "data/delivery_usps_data.xml",
        "views/delivery_usps_view.xml",
        "views/delivery_usps_template.xml",
    ],
}
