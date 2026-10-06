{
    "name": "Timesheet Leaderboard Leave Exclusion",
    "version": "0.1",
    "category": "Sales/Sales",
    "summary": "Exclude leave-linked time entries from timesheet leaderboard calculations",
    "description": "Replaces the leaderboard query with one that excludes analytic lines linked to employee leave or global leave. Billable, total and valid time calculations use the remaining entries; it does not change the underlying timesheets.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sale_timesheet_enterprise",
        "project_timesheet_holidays",
    ],
    "auto_install": True,
}
