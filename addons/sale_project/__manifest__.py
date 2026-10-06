{
    "name": "Sales Projects and Tasks",
    "category": "Sales/Sales",
    "summary": "Create and link projects, tasks and milestones from configured sales services",
    "description": "Adds service-product project and task settings, sales-line links and project creation actions. Supports billable projects and milestone-based delivered quantities alongside related reports and portal extensions. Generation depends on the service tracking policy and configured templates; not every sales order creates a project.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "sale",
        "sale_team",
        "sale_service",
        "project_account",
    ],
    "data": [
        "security/ir.access.csv",
        "views/product_views.xml",
        "views/project_task_views.xml",
        "views/sale_order_line_views.xml",
        "views/sale_order_views.xml",
        "views/sale_project_portal_templates.xml",
        "views/project_update_template.xml",
        "views/project_sharing_views.xml",
        "views/project_views.xml",
        "data/sale_project_data.xml",
        "wizards/wizard_project_project_create_from_template_views.xml",
    ],
    "demo": [
        "demo/sale_project_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_project/static/src/components/**/*",
            "sale_project/static/src/core/**/*",
            "sale_project/static/src/views/**/*",
        ],
        "web.assets_tests": [
            "sale_project/static/tests/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "sale_project/static/tests/*",
        ],
    },
    "auto_install": [
        "sale",
        "project_account",
    ],
    "post_init_hook": "_set_allow_billable_in_project",
    "uninstall_hook": "uninstall_hook",
}
