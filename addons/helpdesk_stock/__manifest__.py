{
    "name": "Helpdesk Returns and Replacements",
    "category": "Services/Helpdesk",
    "summary": "Create and track product returns and replacement transfers from tickets",
    "description": "Adds product and lot selection, return and replacement actions, and links between tickets and stock transfers. The return wizard selects eligible customer deliveries and carries the ticket reference onto the resulting transfer.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "helpdesk_sale",
        "sale_stock",
    ],
    "data": [
        "wizards/wizard_stock_picking_return_views.xml",
        "views/stock_picking_views.xml",
        "views/helpdesk_ticket_views.xml",
        "data/mail_templates.xml",
    ],
    "demo": [
        "demo/helpdesk_stock_demo.xml",
    ],
}
