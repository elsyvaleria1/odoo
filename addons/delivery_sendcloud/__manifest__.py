{
    "name": "Sendcloud Shipping",
    "version": "19.0.2.0.1",
    "oldest_upgradable_version": "19.0.2.0.1",
    "category": "Shipping Connectors",
    "sequence": 316,
    "summary": "Quote and create shipments through Sendcloud",
    "description": "Connect delivery carriers to Sendcloud for shipment rates, shipping requests and tracking links. Requires a provider account and configured service credentials; shipment options depend on the selected carrier service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_delivery",
        "mail",
        "credential",
    ],
    "data": [
        "security/ir.access.csv",
        "data/message_templates.xml",
        "views/delivery_carrier_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_delivery_carrier_update_sendcloud_product_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "delivery_sendcloud/static/src/**/*.js",
            "delivery_sendcloud/static/src/**/*.xml",
        ],
    },
    "application": True,
}
