{
    "name": "Helpdesk Repair Orders",
    "category": "Services/Helpdesk",
    "summary": "Create and access repair orders from helpdesk tickets",
    "description": "Adds repair order links, counts and a repair-creation action on tickets. Ticket information supplies defaults to the repair form; repair operations are implemented by the Repair dependency.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "helpdesk_stock",
        "repair",
    ],
    "data": [
        "views/repair_views.xml",
        "views/helpdesk_ticket_views.xml",
    ],
    "demo": [
        "demo/helpdesk_repair_demo.xml",
    ],
}
