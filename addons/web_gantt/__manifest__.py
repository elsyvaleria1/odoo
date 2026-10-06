{
    "name": "Gantt Views",
    "version": "2.0",
    "category": "Hidden",
    "summary": "Display and reschedule business records in Gantt views",
    "description": "Provide the Gantt view type, grouped data loading and scheduling operations. Supports rescheduling and undo actions for models configured to use the view.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "web",
    ],
    "assets": {
        "web._assets_primary_variables": [
            "web_gantt/static/src/gantt_view.variables.scss",
        ],
        "web.assets_backend": [
            "web_gantt/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "web_gantt/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
