{
    "name": "Planned and Recorded Project Time",
    "version": "1.0",
    "category": "Services/Timesheets",
    "sequence": 50,
    "summary": "Compare project shift allocations with employee timesheet hours and costs",
    "description": "Links planning shifts to timesheets for the same employee and project within the shift date range and adds comparison reports. Matching uses timesheet dates, not clock-time overlap; results depend on recorded timesheets and reporting access.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "timesheet_grid",
        "project_forecast",
    ],
    "data": [
        "reports/planning_analysis_report_views.xml",
        "reports/project_timesheet_forecast_report_analysis_views.xml",
        "security/ir.access.csv",
        "data/ir_filters_data.xml",
        "views/planning_slot_views.xml",
        "views/project_timesheet_forecast_menus.xml",
    ],
    "demo": [
        "demo/planning_slot_demo.xml",
        "demo/account_analytic_line_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "project_timesheet_forecast/static/src/**/*",
        ],
    },
    "auto_install": True,
    "uninstall_hook": "_uninstall_hook",
}
