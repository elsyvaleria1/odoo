{
    "name": "Helpdesk Time Tracking",
    "category": "Services/Helpdesk",
    "summary": "Record timesheets and timer entries against helpdesk tickets",
    "description": "Adds a timesheet project on helpdesk teams, ticket time entries and timers, and time totals in ticket analysis. Requires timesheets enabled on the team and its project; sales billing is provided by a separate extension.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "timesheet_grid",
        "project_helpdesk",
    ],
    "data": [
        "security/helpdesk_timesheet_security.xml",
        "security/ir.access.csv",
        "views/helpdesk_team_views.xml",
        "views/helpdesk_ticket_views.xml",
        "views/project_project_views.xml",
        "views/hr_timesheet_views.xml",
        "reports/helpdesk_sla_report_analysis_views.xml",
        "reports/helpdesk_ticket_report_analysis_views.xml",
        "reports/report_timesheet_templates.xml",
        "reports/timesheets_analysis_report_views.xml",
    ],
    "demo": [
        "demo/project_project_demo.xml",
        "demo/helpdesk_team_demo.xml",
        "demo/helpdesk_ticket_demo.xml",
        "demo/account_analytic_line_demo.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "helpdesk_timesheet/static/tests/tours/**",
        ],
        "web.assets_backend": [
            "helpdesk_timesheet/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "helpdesk_timesheet/static/tests/*",
        ],
    },
    "post_init_hook": "_helpdesk_timesheet_post_init",
    "uninstall_hook": "_helpdesk_timesheet_uninstall",
}
