{
    "name": "Project Assignee Time Off",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Show task warnings when assignees are absent",
    "description": "Adds leave warnings, absence searching and time-off grouping to task views using the employee leave records.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "project_gantt",
        "hr_holidays_gantt",
    ],
    "data": [
        "views/project_task_views.xml",
    ],
    "auto_install": True,
}
