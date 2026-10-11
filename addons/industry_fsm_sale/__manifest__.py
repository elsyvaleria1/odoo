{
    "name": "Field Service Sales",
    "version": "1.0",
    "category": "Services/Field Service",
    "summary": "Link field-service tasks to quotations, material lines and invoicing",
    "description": "Adds quotation and invoice links to field-service tasks and exposes a product catalog for recording task materials on sales orders. Connects task timesheets to sales lines and supports task-related invoicing actions. Uses the sales and timesheet dependencies for billing calculations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "industry_fsm",
        "sale_timesheet_enterprise",
    ],
    "data": [
        "data/industry_fsm_data.xml",
        "reports/report_project_task_user_fsm_views.xml",
        "reports/worksheet_custom_report_templates.xml",
        "views/project_task_views.xml",
        "views/product_product_views.xml",
        "views/project_project_views.xml",
        "views/sale_order_views.xml",
        "views/project_sharing_views.xml",
        "views/project_portal_templates.xml",
        "views/industry_fsm_sale_menus.xml",
    ],
    "demo": [
        "demo/industry_fsm_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "industry_fsm_sale/static/src/components/**/*",
            "industry_fsm_sale/static/src/js/tours/**/*",
        ],
        "web.assets_tests": [
            "industry_fsm_sale/static/tests/tours/**/*",
        ],
        "web.assets_frontend": [
            "industry_fsm_sale/static/src/js/tours/**/*",
        ],
        "web.assets_unit_tests": [
            "industry_fsm_sale/static/tests/product_catalog.test.js",
            "industry_fsm_sale/static/tests/industry_fsm_sale_mock_model.js",
        ],
    },
    "auto_install": True,
    "post_init_hook": "post_init",
    "uninstall_hook": "uninstall_hook",
}
