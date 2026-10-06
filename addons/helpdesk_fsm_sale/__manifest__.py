{
    "name": "Helpdesk Field Service Sales Items",
    "category": "Services/Helpdesk",
    "summary": "Carry a ticket sales order item onto its generated field service task",
    "description": "Extends the ticket task-creation wizard to copy sale_line_id when the source ticket has one. Sales billing and field service workflows are supplied by the dependencies.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "helpdesk_fsm",
        "helpdesk_sale_timesheet",
        "industry_fsm_sale",
    ],
    "data": [
        "views/project_project_views.xml",
    ],
    "auto_install": True,
}
