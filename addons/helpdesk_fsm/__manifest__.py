{
    "name": "Helpdesk Field Service Tasks",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Services/Helpdesk",
    "summary": "Create field service tasks from helpdesk tickets",
    "description": "Adds a task-creation wizard, task links and a default field service project on helpdesk teams. Creating a task requires a customer and a field service project; the ticket remains linked to the generated task.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "project_helpdesk",
        "industry_fsm",
    ],
    "data": [
        "security/ir.access.csv",
        "data/mail_message_subtype_data.xml",
        "views/helpdesk_ticket_views.xml",
        "views/helpdesk_team_views.xml",
        "views/project_sharing_views.xml",
        "views/project_task_views.xml",
        "wizards/wizard_helpdesk_ticket_create_fsm_task_views.xml",
    ],
    "demo": [
        "demo/helpdesk_fsm_demo.xml",
    ],
    "auto_install": True,
}
