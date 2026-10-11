{
    "name": "Database Portfolio",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Services/Databases",
    "summary": "Track connected Odoo databases and retrieve their available information",
    "description": "Extends projects with database connection details, synchronization actions and remote user-management tools. Reads supported remote information through authenticated API calls. Requires reachable compatible databases and credentials with the permissions needed for each operation.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "credential",
        "project",
    ],
    "data": [
        "security/databases_security.xml",
        "security/ir.access.csv",
        "security/ir_access.xml",
        "data/ir_cron.xml",
        "data/project_template.xml",
        "views/databases_project_views.xml",
        "views/databases_menus.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_project_project_update_database_user_views.xml",
        "wizards/wizard_project_project_synchronize_database_views.xml",
        "wizards/wizard_project_project_create_from_template_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "databases/static/src/views/databases_project_list/databases_project_list_renderer.js",
            "databases/static/src/views/databases_project_list/databases_project_list_view.js",
        ],
        "web.assets_tests": [
            "databases/static/tests/tours/**/*",
        ],
    },
    "application": True,
    "uninstall_hook": "uninstall_hook",
}
