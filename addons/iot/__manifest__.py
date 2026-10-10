{
    "name": "Internet of Things",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Supply Chain/IoT",
    "sequence": 250,
    "summary": "Register IoT boxes and devices and connect browser actions to them",
    "description": "Adds IoT box and device records linked to the shared device registry, pairing routes, handler delivery and browser communication support. Connects reports to selected printing devices. Requires a reachable IoT runtime and suitable installed device handlers for the hardware being used.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "device",
        "integration",
        "mail",
    ],
    "data": [
        "data/device_kind_data.xml",
        "wizards/wizard_iot_box_pair_views.xml",
        "wizards/wizard_ir_actions_report_print_iot_views.xml",
        "security/iot_security.xml",
        "security/ir.access.csv",
        "security/ir_access.xml",
        "views/iot_views.xml",
        "views/iot_menus.xml",
    ],
    "demo": [
        "demo/iot_demo.xml",
    ],
    "assets": {
        "iot.assets_client": [
            "iot/static/src/network_utils/**/*",
            "iot/static/src/device_controller.js",
            "iot/static/src/device_messages.js",
        ],
        "iot.assets_report": [
            "iot/static/src/iot_report_action.js",
            "iot/static/src/select_printer_wizard.js",
            "iot/static/src/client_action/delete_local_storage.js",
        ],
        "web.assets_backend": [
            (
                "include",
                "iot.assets_client",
            ),
            (
                "include",
                "iot.assets_report",
            ),
            "iot/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "iot/static/tests/unit/**/*",
        ],
        "web.assets_tests": [
            (
                "include",
                "iot.assets_tests",
            ),
        ],
        "iot.assets_tests": [
            "iot/static/tests/tours/**/*",
        ],
    },
    "application": True,
}
