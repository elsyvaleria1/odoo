{
    "name": "Shiprocket Shipping",
    "version": "19.0.2.0.0",
    "oldest_upgradable_version": "19.0.2.0.0",
    "category": "Shipping Connectors",
    "sequence": 317,
    "summary": "Quote and create shipments through Shiprocket",
    "description": "Connect delivery carriers to Shiprocket for shipment rates, shipping requests and tracking links. Requires a provider account and configured service credentials; shipment options depend on the selected carrier service.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_delivery",
        "mail",
        "credential",
    ],
    "data": [
        "security/ir.access.csv",
        "data/data.xml",
        "views/res_config_settings_views.xml",
        "views/delivery_carrier_views.xml",
        "views/stock_picking.xml",
    ],
    "application": True,
}
