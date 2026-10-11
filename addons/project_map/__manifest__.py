{
    "name": "Project Task Map",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Display project tasks on a map",
    "description": "Adds task map views, assignee names and map navigation actions using the geographic data available on the task contacts.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "project",
        "web_map",
    ],
    "data": [
        "views/project_task_views.xml",
        "data/project_view_mode.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "project_map/static/src/views/project_task_map/**",
        ],
        "web.assets_unit_tests": [
            "project_map/static/tests/*",
        ],
    },
    "auto_install": True,
    "uninstall_hook": "_project_map_uninstall_hook",
}
