{
    "name": "Mailbox Helpdesk Ticket Actions",
    "version": "1.0",
    "category": "Services/Helpdesk",
    "summary": "Create helpdesk tickets from email content through the mailbox integration",
    "description": "Adds an authenticated mail-plugin ticket-creation endpoint and contact ticket listings. The endpoint requires an existing contact and ticket creation rights; mail content logging extends the plugin model whitelist. A compatible configured mailbox client is required.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "helpdesk",
        "mail_plugin",
    ],
    "data": [
        "views/helpdesk_ticket_views.xml",
    ],
    "auto_install": True,
}
