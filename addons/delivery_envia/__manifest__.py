{
    "name": "Envia Shipping",
    "version": "19.0.2.0.1",
    "oldest_upgradable_version": "19.0.2.0.1",
    "category": "Shipping Connectors",
    "summary": "Quote and create shipments through Envia",
    "description": "Connect delivery carriers to Envia for shipment rates, shipping requests and tracking links. Requires a provider account and configured service credentials; shipment options depend on the selected carrier service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock_delivery",
        "partner_address_extended",
        "phone_validation",
        "credential",
    ],
    "data": [
        "security/ir.access.csv",
        "data/delivery_envia.xml",
        "views/delivery_carrier_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_delivery_carrier_update_envia_service_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "delivery_envia/static/src/components/**/*.js",
            "delivery_envia/static/src/components/**/*.xml",
        ],
    },
    "application": True,
}
