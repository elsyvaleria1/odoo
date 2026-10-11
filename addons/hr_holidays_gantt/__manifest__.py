{
    "name": "Time Off Timeline",
    "version": "1.0",
    "category": "Human Resources",
    "summary": "Review employee time off on a timeline",
    "description": "Adds time-off Gantt views and frontend handling for employee leave periods.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_holidays",
        "hr_gantt",
    ],
    "data": [
        "views/hr_holidays_gantt_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_holidays_gantt/static/src/**/*",
        ],
    },
    "auto_install": True,
}
