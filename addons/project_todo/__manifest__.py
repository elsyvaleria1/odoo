{
    "name": "Personal To-Do Tasks",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Productivity/To-Do",
    "sequence": 260,
    "summary": "Manage personal to-do items and convert them into project tasks",
    "description": "Provides personal task views, onboarding items and a creation wizard with assignee and deadline. Selected to-do items can be converted into project tasks.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "project",
    ],
    "data": [
        "security/ir.access.csv",
        "data/todo_template.xml",
        "views/project_task_views.xml",
        "views/project_todo_menus.xml",
        "wizards/wizard_project_task_create_todo_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "project_todo/static/src/components/**/*",
            "project_todo/static/src/scss/todo.scss",
            "project_todo/static/src/views/**/*",
            "project_todo/static/src/web/**/*",
        ],
        "web.assets_tests": [
            "project_todo/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "project_todo/static/tests/**/*",
        ],
    },
    "application": True,
    "auto_install": True,
    "post_init_hook": "_todo_post_init",
}
