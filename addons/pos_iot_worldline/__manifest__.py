{
    "name": "POS Worldline IoT Payments",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "summary": "Process POS payments through Worldline terminals connected to IoT",
    "description": "Adds a Worldline terminal choice and POS payment interface for the IoT integration. Requires a supported terminal connected to a configured IoT installation.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "iot_worldline",
        "pos_iot",
    ],
    "data": [
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_iot_worldline/static/src/**/*",
        ],
    },
}
