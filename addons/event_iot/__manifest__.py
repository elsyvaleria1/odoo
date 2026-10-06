{
    "name": "Event Badge IoT Printing",
    "version": "1.0",
    "category": "Marketing/Events",
    "summary": "Print event registration badges through compatible IoT printers",
    "description": "Adds a 96x82 mm badge format, printer report templates and check-in printing integration. Requires a configured compatible printer and IoT connection; the supplied printer report emits ESC/Label commands.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "iot",
        "event",
    ],
    "data": [
        "reports/event_iot_templates.xml",
        "reports/event_iot_reports.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "event_iot/static/src/**/*",
        ],
    },
    "auto_install": True,
}
