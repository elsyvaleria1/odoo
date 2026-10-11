{
    "name": "Call Ticket Links",
    "version": "1.0",
    "category": "Services/Helpdesk",
    "summary": "Open customer helpdesk tickets from phone calls",
    "description": "Adds total and open-ticket counts and ticket navigation to call records.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "voip",
        "helpdesk",
    ],
    "data": [
        "views/phone_call_views.xml",
    ],
    "auto_install": True,
}
