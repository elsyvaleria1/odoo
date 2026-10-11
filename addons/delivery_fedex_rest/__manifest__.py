{
    "name": "FedEx Shipping",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Shipping Connectors",
    "summary": "Quote and create shipments through FedEx",
    "description": "Connect delivery carriers to FedEx for shipment rates, shipping requests and tracking links. Requires a provider account and configured service credentials; shipment options depend on the selected carrier service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_delivery",
        "mail",
    ],
    "data": [
        "data/delivery_fedex.xml",
        "views/delivery_fedex.xml",
    ],
    "application": True,
}
