{
    "name": "Self-Order IoT Devices",
    "version": "1.0.0",
    "category": "Sales/Point of Sale",
    "summary": "Connect self-order kiosks to configured IoT devices",
    "description": "Loads IoT box configuration for kiosks and handles device payment results and cancellation. Requires a configured compatible IoT installation.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "pos_iot",
        "pos_self_order",
    ],
    "data": [
        "views/iot_views.xml",
        "views/res_config_settings.xml",
    ],
    "demo": [
        "demo/iot_demo.xml",
    ],
    "assets": {
        "pos_self_order.assets": [
            (
                "include",
                "iot.assets_client",
            ),
            "pos_iot/static/src/app/utils/printer/iot_printer.js",
            "pos_iot/static/src/overrides/network_utils/iot_http_service.js",
            "point_of_sale/static/src/app/services/hardware_proxy_service.js",
            "pos_self_order_iot/static/src/overrides/models/*",
            "pos_self_order_iot/static/src/overrides/network_utils/*",
            "pos_self_order_iot/static/src/pages/**/*",
        ],
        "web.assets_backend": [
            "pos_self_order_iot/static/src/views/*",
        ],
        "pos_self_order.assets_tests": [
            (
                "include",
                "iot.assets_tests",
            ),
            "pos_self_order_iot/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
