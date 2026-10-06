{
    "name": "Approval Analytics",
    "version": "19.0.1.0.1",
    "category": "Human Resources/Approvals",
    "sequence": 191,
    "summary": "Report approval outcomes, elapsed times and approver workload",
    "description": "Adds category and approver SQL reports plus dashboard metrics and reporting menus for the Approvals application. Calculates request-state counts, approval and response times, workload and configured SLA comparisons from approval records; results depend on recorded workflow dates and category targets.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "approval_app",
        "mixin_report_sql",
    ],
    "data": [
        "security/ir.access.csv",
        "views/approval_dashboard_views.xml",
        "views/approval_metrics_views.xml",
        "views/approver_performance_views.xml",
        "views/approval_analytics_menuitem_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "approval_analytics/static/src/scss/approval_dashboard.scss",
            "approval_analytics/static/src/scss/approval_dashboard.scheme_rules.scss",
        ],
    },
    "auto_install": True,
}
