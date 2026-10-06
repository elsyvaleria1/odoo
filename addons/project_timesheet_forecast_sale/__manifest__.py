{
    "name": "Project Planned and Recorded Hours",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Compare planned shifts and recorded timesheets for sold project work",
    "description": "Connect sales line planning hours, project shifts and analytic timesheet entries. Provides planning and timesheet analysis views with project drill-down actions.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/project",
    "license": "OEEL-1",
    "depends": [
        "project_timesheet_forecast",
        "sale_timesheet",
        "sale_project_forecast",
    ],
    "data": [
        "views/planning_slot_views.xml",
        "views/project_project_views.xml",
        "reports/planning_analysis_report_views.xml",
        "reports/project_timesheet_forecast_report_analysis_views.xml",
    ],
    "demo": [
        "demo/planning_role_demo.xml",
        "demo/hr_employee_demo.xml",
        "demo/product_product_demo.xml",
        "demo/sale_order_line_demo.xml",
    ],
    "auto_install": True,
}
