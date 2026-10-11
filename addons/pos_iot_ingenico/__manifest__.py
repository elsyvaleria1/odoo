{
    "name": "POS Ingenico IoT Payments",
    "version": "1.0",
    "category": "Sales/Point of Sale",
    "summary": "Process POS payments through Ingenico terminals connected to IoT",
    "description": "Adds a Ingenico terminal choice and POS payment interface for the IoT integration. Requires a supported terminal connected to a configured IoT installation.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "iot_ingenico",
        "pos_iot",
    ],
    "data": [
        "views/pos_payment_method_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_iot_ingenico/static/src/**/*",
        ],
    },
}
