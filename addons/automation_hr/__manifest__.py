{
    "name": "Employee Calendar Automation",
    "version": "1.1",
    "category": "Human Resources",
    "summary": "Use employee contract calendars when evaluating automation rules",
    "description": "Extend automation calendar selection for employee-related rules. Adds the corresponding rule configuration view.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "automation",
        "hr",
    ],
    "data": [
        "views/automation_rule_views.xml",
    ],
    "auto_install": True,
}
