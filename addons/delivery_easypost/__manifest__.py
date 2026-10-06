{
    "name": "EasyPost Shipping",
    "version": "19.0.2.0.1",
    "oldest_upgradable_version": "19.0.2.0.1",
    "category": "Shipping Connectors",
    "sequence": 315,
    "summary": "Quote and create shipments through EasyPost",
    "description": "Connect delivery carriers to EasyPost for shipment rates, shipping requests and tracking links. Requires a provider account and configured service credentials; shipment options depend on the selected carrier service.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_delivery",
        "mail",
        "credential",
    ],
    "data": [
        "security/ir.access.csv",
        "views/delivery_carrier_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_delivery_carrier_update_easypost_type_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "delivery_easypost/static/src/components/**/*",
        ],
        "web.assets_tests": [
            "delivery_easypost/static/tests/tours/**/*",
        ],
    },
    "application": True,
}
