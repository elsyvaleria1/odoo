{
    "name": "Helpdesk Sales Order Links",
    "category": "Services/Helpdesk",
    "summary": "Link helpdesk tickets and analysis reports to sales orders",
    "description": "Adds a sales order reference and order state on tickets and exposes that reference in ticket and SLA analysis. It supplies sales context for other after-sales extensions; it does not itself create returns or credit notes.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "helpdesk",
        "sale",
    ],
    "data": [
        "security/helpdesk_security.xml",
        "views/helpdesk_ticket_views.xml",
        "views/helpdesk_sla_views.xml",
    ],
    "demo": [
        "demo/helpdesk_sale_demo.xml",
    ],
    "auto_install": True,
}
