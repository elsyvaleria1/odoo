{
    "name": "POS IoT Device Integration",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "sequence": 6,
    "summary": "Connect POS sessions to configured IoT printers, scales, displays and payment devices",
    "description": "Adds POS device selection, IoT data loading and frontend device integration. Requires compatible hardware, its IoT driver and a configured connection; individual payment terminal protocols may require dedicated terminal addons.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "point_of_sale",
        "iot",
    ],
    "data": [
        "views/iot_views.xml",
        "views/pos_config_views.xml",
        "views/pos_printer_views.xml",
        "views/res_config_setting_views.xml",
        "wizards/wizard_pos_config_update_iot_device_views.xml",
        "security/ir.access.csv",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            (
                "include",
                "iot.assets_client",
            ),
            (
                "include",
                "iot.assets_report",
            ),
            "pos_iot/static/src/app/**/*",
            "pos_iot/static/src/overrides/**/*",
        ],
        "web.assets_tests": [
            "pos_iot/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "pos_iot/static/tests/unit/**/*",
        ],
        "web.assets_backend": [
            "pos_iot/static/src/backend/**/*",
        ],
    },
    "auto_install": True,
    "uninstall_hook": "uninstall_hook",
}
