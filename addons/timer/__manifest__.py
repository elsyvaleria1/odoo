{
    "name": "Record Timer Infrastructure",
    "version": "1.0",
    "category": "Services/Timesheets",
    "sequence": 24,
    "summary": "Provide start, stop, pause and resume timers for adopting models",
    "description": "Defines timer records, reusable model mixins and interface components for elapsed-time tracking. Application models must adopt the mixins and connect timer actions to their workflow; this addon supplies the shared timer infrastructure.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "web",
        "mail",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "timer/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "timer/static/tests/**/*",
        ],
    },
}
