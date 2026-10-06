{
    "name": "Mondial Relay Pickup Selection",
    "version": "0.1",
    "category": "Shipping Connectors",
    "summary": "Select a Mondial Relay pickup point as the shipping address",
    "description": "Integrates the pickup-point selection widget and stores the selected address. It does not implement the shipping web service; the supplied example delivery pricing must be configured for the deployment.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "stock_delivery",
    ],
    "data": [
        "data/data.xml",
        "views/portal_address_templates.xml",
        "views/views.xml",
        "wizards/wizard_sale_order_add_shipping_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "delivery_mondialrelay/static/src/components/**/*.js",
            "delivery_mondialrelay/static/src/scss/mondialrelay.scss",
        ],
    },
}
