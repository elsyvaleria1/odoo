{
    "name": "Helpdesk Time Off Availability",
    "version": "1.0",
    "category": "Services/Helpdesk",
    "sequence": 50,
    "summary": "Subtract employee leave from helpdesk assignment availability",
    "description": "Extends working-user interval calculation with employee leave intervals when leave computation is requested. Adds the time-off integration to helpdesk team configuration; it does not manage leave approval.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "helpdesk",
        "hr_holidays_gantt",
    ],
    "data": [
        "views/helpdesk_team_view.xml",
    ],
    "auto_install": True,
}
