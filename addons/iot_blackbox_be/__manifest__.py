{
    "name": "IoT - Belgian Fiscal Device Driver",
    "category": "Supply Chain/IoT",
    "summary": "Exchange receipt, PIN and status messages with a Belgian fiscal data module",
    "description": "Adds the serial device handler, message framing, receipt-registration actions and response parsing for the supported fiscal data module. Requires compatible hardware and an IoT runtime. The point-of-sale fiscal integration supplies business receipt data; installing this driver is not fiscal certification.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "iot",
    ],
    "assets": {
        "iot_blackbox_be.assets_messages": [
            "iot_blackbox_be/static/src/fdm_messages.js",
        ],
        "web.assets_backend": [
            (
                "include",
                "iot_blackbox_be.assets_messages",
            ),
        ],
        "web.assets_unit_tests": [
            "iot_blackbox_be/static/tests/**/*",
        ],
    },
    "iot_handlers_in_image": True,
    "auto_install": True,
}
