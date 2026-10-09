{
    "name": "Notification Bus",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Deliver server notifications to subscribed browser clients",
    "description": "Provide notification channels, message delivery and websocket session handling. Applications publish messages to channels and clients subscribe to the channels they use.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "web",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "bus/static/src/*.js",
            "bus/static/src/debug/**/*",
            "bus/static/src/services/**/*.js",
            "bus/static/src/workers/*",
            (
                "remove",
                "bus/static/src/workers/bus_worker_script.js",
            ),
        ],
        "web.assets_frontend": [
            "bus/static/src/*.js",
            "bus/static/src/public/**/*",
            "bus/static/src/services/**/*.js",
            (
                "remove",
                "bus/static/src/services/assets_watchdog_service.js",
            ),
            (
                "remove",
                "bus/static/src/simple_notification_service.js",
            ),
            "bus/static/src/workers/*",
            (
                "remove",
                "bus/static/src/workers/bus_worker_script.js",
            ),
        ],
        "web.assets_unit_tests": [
            "bus/static/tests/**/*",
        ],
        "web.assets_unit_tests_setup": [
            "bus/static/src/public/**/*",
        ],
        "bus.websocket_worker_assets": [
            "bus/static/src/workers/*",
        ],
    },
    "esm": {
        "bundles": [
            "bus.websocket_worker_assets",
        ],
        "standalone_bundles": [
            "bus.websocket_worker_assets",
        ],
    },
    "auto_install": True,
}
