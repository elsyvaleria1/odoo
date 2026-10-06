{
    "name": "Sales Timesheet Validation and Billing",
    "version": "0.1",
    "category": "Sales/Sales",
    "summary": "Configure whether timesheet billing uses all eligible time or only validated entries",
    "description": "Extends sales timesheet quantities and invoiced-line selection with an optional validated-only filter; the default includes all otherwise eligible timesheets. Adds billing targets, ranking, project-sharing displays and invoicing controls alongside the timesheet grid dependency.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sale_timesheet",
        "timesheet_grid",
    ],
    "data": [
        "data/hr_employee_tip_data.xml",
        "data/ir_exports_line_data.xml",
        "security/ir.access.csv",
        "views/account_move_views.xml",
        "views/hr_timesheet_tip_views.xml",
        "views/hr_timesheet_views.xml",
        "views/hr_employee_views.xml",
        "views/project_task_views.xml",
        "views/project_sharing_project_task_views.xml",
        "views/res_config_settings_views.xml",
        "views/project_portal_project_task_template.xml",
        "wizards/wizard_sale_order_invoice_views.xml",
        "wizards/edit_billable_time_target_views.xml",
        "reports/timesheets_analysis_report_views.xml",
        "views/sale_timesheet_enterprise_menus.xml",
    ],
    "demo": [
        "demo/account_analytic_line_demo.xml",
        "demo/hr_employee_demo.xml",
        "demo/project_task_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_timesheet_enterprise/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "sale_timesheet_enterprise/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
