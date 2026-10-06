{
    "name": "USPS Shipping",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Shipping Connectors",
    "sequence": 305,
    "summary": "Quote and create shipments through USPS",
    "description": "Connect delivery carriers to USPS for shipment rates, shipping requests and tracking links. Requires a provider account and configured service credentials; shipment options depend on the selected carrier service.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_delivery",
        "mail",
    ],
    "data": [
        "data/delivery_usps_data.xml",
        "views/delivery_usps_view.xml",
    ],
    "application": True,
}
