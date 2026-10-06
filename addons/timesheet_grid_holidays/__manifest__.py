{
    "name": "Time-Off Timesheet Grid Restrictions",
    "version": "1.0",
    "category": "Services/Timesheets",
    "summary": "Protect leave-linked timesheets from grid edits, merges and timer entry",
    "description": "Excludes leave-linked lines from grid cell updates and refuses merging those lines, with a Time Off redirect for eligible users. Hides and blocks timers on time-off tasks; leave creation and timesheet generation are supplied by the dependencies.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "project_timesheet_holidays",
        "timesheet_grid",
    ],
    "assets": {
        "web.assets_backend": [
            "timesheet_grid_holidays/static/src/**/*",
        ],
    },
    "auto_install": True,
}
