{
    "name": "Time-Off Timesheet Generation",
    "version": "1.2",
    "oldest_upgradable_version": "1.1",
    "category": "Human Resources",
    "summary": "Generate timesheets for eligible employee leave and public holidays",
    "description": "Creates leave-linked time entries using configured company projects and tasks, employee schedules and eligible non-work leave types. Updates or removes linked entries as leave and public-holiday records change; the module also restricts direct edits to generated entries.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_timesheet",
        "hr_holidays",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/project_task_views.xml",
        "security/ir.access.csv",
    ],
    "demo": [
        "demo/holiday_timesheets_demo.xml",
    ],
    "auto_install": True,
    "post_init_hook": "post_init",
}
