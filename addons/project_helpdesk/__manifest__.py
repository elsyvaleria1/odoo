{
    "name": "Task and Ticket Conversion",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Services/Helpdesk",
    "summary": "Convert helpdesk tickets into tasks and tasks into tickets",
    "description": "Provides conversion wizards with destination project or helpdesk team and stage selection.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "project",
        "helpdesk",
    ],
    "data": [
        "security/ir.access.csv",
        "views/helpdesk_ticket_views.xml",
        "views/project_task_views.xml",
        "wizards/wizard_helpdesk_ticket_convert_task_views.xml",
        "wizards/wizard_project_task_convert_ticket_views.xml",
    ],
    "demo": [
        "demo/helpdesk_ticket_demo.xml",
        "demo/helpdesk_ticket_convert_wizard_demo.xml",
        "demo/project_task_demo.xml",
        "demo/mail_message_demo.xml",
        "demo/project_task_convert_wizard_demo.xml",
    ],
    "auto_install": True,
}
