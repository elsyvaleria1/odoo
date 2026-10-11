{
    "name": "DHL Express Shipping",
    "version": "19.0.2.0.0",
    "oldest_upgradable_version": "19.0.2.0.0",
    "category": "Shipping Connectors",
    "summary": "Quote and create shipments through DHL Express",
    "description": "Connect delivery carriers to DHL Express for shipment rates, shipping requests and tracking links. Requires a provider account and configured service credentials; shipment options depend on the selected carrier service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_delivery",
        "mail",
        "credential",
    ],
    "data": [
        "data/delivery_dhl_data.xml",
        "views/delivery_dhl_view.xml",
    ],
    "demo": [
        "demo/demo.xml",
    ],
    "application": True,
}
