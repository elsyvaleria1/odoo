{
    "name": "Helpdesk Timesheet Billing",
    "category": "Services/Helpdesk",
    "summary": "Link ticket timesheets to billable sales order items",
    "description": "Adds sales order item selection, remaining sold hours and invoice navigation to helpdesk tickets. Timesheet billing requires the team time-billing feature and an eligible service sales order item; invoicing uses the sales and timesheet dependencies.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "helpdesk_timesheet",
        "sale_timesheet_enterprise",
        "helpdesk_sale",
    ],
    "data": [
        "views/hr_timesheet_views.xml",
        "views/helpdesk_team_views.xml",
        "views/helpdesk_ticket_views.xml",
        "views/helpdesk_sla_views.xml",
        "views/helpdesk_portal_templates.xml",
        "views/project_project_views.xml",
        "views/sale_order_views.xml",
        "reports/helpdesk_ticket_analysis_views.xml",
        "reports/helpdesk_sla_analysis_views.xml",
    ],
    "demo": [
        "demo/helpdesk_sale_timesheet_demo.xml",
    ],
    "auto_install": True,
    "post_init_hook": "_helpdesk_sale_timesheet_post_init",
}
