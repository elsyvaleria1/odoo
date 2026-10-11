{
    "name": "Helpdesk Field Service Worksheets",
    "category": "Services/Helpdesk",
    "summary": "Select worksheet templates when creating field service tasks from tickets",
    "description": "Extends the ticket task-creation wizard with a worksheet template defaulted from the selected project. The chosen template is copied to the generated task when that project allows worksheets.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "helpdesk_fsm",
        "industry_fsm_report",
    ],
    "data": [
        "wizards/wizard_helpdesk_ticket_create_fsm_task_views.xml",
    ],
    "auto_install": True,
}
