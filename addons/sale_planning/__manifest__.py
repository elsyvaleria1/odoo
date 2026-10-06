{
    "name": "Sales Shift Planning",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Sales",
    "summary": "Create planned shifts for sold services with planning enabled",
    "description": """
This module allows you to schedule your Sales Order based on the product configuration.

For products on which the "Plan Services" option is enabled, you will have the opportunity
to automatically plan the shifts for employees whom are able to take the shift
(i.e. employees who have the same role as the one configured on the product).

Plan shifts and keep an eye on the hours consumed on your plannable products.
    """,
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sale",
        "sale_team",
        "sale_service",
        "planning",
    ],
    "data": [
        "security/ir.access.csv",
        "data/planning_role_data.xml",
        "views/planning_role_views.xml",
        "views/planning_slot_views.xml",
        "views/planning_templates.xml",
        "views/product_views.xml",
        "views/sale_order_views.xml",
        "views/sale_planning_menus.xml",
    ],
    "demo": [
        "demo/product_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_planning/static/src/components/**/*",
            "sale_planning/static/src/views/planning_hooks.js",
            "sale_planning/static/src/views/sale_planning_gantt/**",
        ],
        "web.assets_frontend": [
            "sale_planning/static/src/js/frontend/**/*",
        ],
        "web.assets_tests": [
            "sale_planning/static/tests/tours/*",
        ],
        "web.assets_unit_tests": [
            "sale_planning/static/tests/*",
        ],
    },
    "auto_install": [
        "sale",
        "planning",
    ],
    "uninstall_hook": "uninstall_hook",
}
