{
    "name": "Project Employee Assignments",
    "version": "1.4",
    "oldest_upgradable_version": "1.4",
    "category": "Services/Project",
    "summary": "Assign employees to projects and tasks and derive their linked users",
    "description": "Adds employee assignment fields, views and scheduling integration to projects and tasks. Task users combine employee-linked users with direct user assignments; project managers derive from selected employees. Installation backfills employee associations where possible, and subsequent employee user changes update linked assignments.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "project",
        "hr",
    ],
    "data": [
        "views/project_task_views.xml",
        "views/project_project_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "project_hr/static/src/js/tours/project.js",
        ],
        "web.assets_tests": [
            "project_hr/static/tests/tours/**/*",
        ],
    },
    "post_init_hook": "post_init_hook",
}
