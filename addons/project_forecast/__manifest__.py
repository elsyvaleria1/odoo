{
    "name": "Project Shift Planning",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Services/Project",
    "summary": "Associate planning shifts and templates with projects",
    "description": "Adds project selection to planning slots and shift templates, project planned-hour totals, project reporting dimensions and project information on shared schedules. Requires Planning and Project; this addon does not predict project completion dates.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "project",
        "planning",
        "web_grid",
    ],
    "data": [
        "security/ir.access.csv",
        "security/ir_access.xml",
        "views/planning_slot_template_views.xml",
        "views/planning_slot_templates.xml",
        "views/planning_slot_views.xml",
        "views/project_project_views.xml",
        "views/planning_menus.xml",
    ],
    "demo": [
        "demo/planning_role_demo.xml",
        "demo/planning_slot_template_demo.xml",
        "demo/planning_slot_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "project_forecast/static/src/components/**/*",
            "project_forecast/static/src/views/**/*",
        ],
        "web.assets_frontend": [
            "project_forecast/static/src/js/forecast_calendar_front.js",
        ],
        "web.assets_unit_tests": [
            "project_forecast/static/tests/**/*",
        ],
        "web.assets_tests": [
            "project_forecast/static/tests/tours/*",
        ],
    },
    "uninstall_hook": "_uninstall_hook",
}
