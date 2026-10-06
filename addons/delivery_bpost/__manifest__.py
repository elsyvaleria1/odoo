{
    "name": "bpost Shipping",
    "version": "19.0.2.0.0",
    "oldest_upgradable_version": "19.0.2.0.0",
    "category": "Shipping Connectors",
    "sequence": 330,
    "summary": "Quote and create shipments through bpost",
    "description": "Connect delivery carriers to bpost for shipment rates, shipping requests and tracking links. Requires a provider account and configured service credentials; shipment options depend on the selected carrier service.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_delivery",
        "mail",
        "credential",
    ],
    "external_dependencies": {
        "python": [
            "defusedxml",
        ],
        "apt": {
            "defusedxml": "python3-defusedxml",
        },
    },
    "data": [
        "data/delivery_bpost_data.xml",
        "views/delivery_bpost_views.xml",
        "views/res_config_settings_views.xml",
        "views/bpost_request_templates.xml",
    ],
    "application": True,
}
