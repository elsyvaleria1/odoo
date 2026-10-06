{
    "name": "Starshipit Shipping",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Shipping Connectors",
    "summary": "Quote and create shipments through Starshipit",
    "description": "Connect delivery carriers to Starshipit for shipment rates, shipping requests and tracking links. Requires a provider account and configured service credentials; shipment options depend on the selected carrier service.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_delivery",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "security/ir.access.csv",
        "views/delivery_carrier_views.xml",
        "views/res_config_settings_views.xml",
        "views/stock_picking_views.xml",
        "wizards/wizard_delivery_carrier_update_starshipit_service_views.xml",
        "wizards/wizard_sale_order_add_shipping_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "delivery_starshipit/static/src/components/**/*.js",
            "delivery_starshipit/static/src/components/**/*.xml",
        ],
    },
    "application": True,
}
