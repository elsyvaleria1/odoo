{
    "name": "Project Timeline Scheduling",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Schedule project tasks on a timeline with dependency constraints",
    "description": "Adds project and task Gantt views, resource availability, workload indicators and dependent-task rescheduling, including shared project views.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "project",
        "web_gantt",
    ],
    "data": [
        "views/project_task_views.xml",
        "views/project_views.xml",
        "views/project_sharing_views.xml",
        "data/project_view_mode.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "project_gantt/static/src/views/view_dialogs/**",
            "project_gantt/static/src/views/project_task_common/**",
            "project_gantt/static/src/views/task_gantt/**",
            "project_gantt/static/src/views/project_gantt/**",
        ],
        "web.assets_unit_tests": [
            "project_gantt/static/tests/*",
        ],
        "project_gantt.project_sharing_unit_tests": [
            "project/static/src/project_sharing/views/**",
            "project/static/src/project_sharing/project_sharing.js",
            "project/static/src/project_sharing/project_sharing.xml",
            "project_gantt/static/src/views/task_sharing_gantt/**",
        ],
        "project.webclient": [
            "web_gantt/static/src/**/*",
            "project_gantt/static/src/views/view_dialogs/**",
            "project_gantt/static/src/views/project_task_common/**",
            "project_gantt/static/src/views/task_sharing_gantt/**",
        ],
        "web.assets_tests": [
            "project_gantt/static/tests/tours/**/*",
        ],
    },
    "esm": {
        "bundles": [
            "project_gantt.project_sharing_unit_tests",
        ],
        "runtime_bundles": [
            "project_gantt.project_sharing_unit_tests",
        ],
    },
    "auto_install": True,
    "uninstall_hook": "_project_gantt_uninstall_hook",
}
