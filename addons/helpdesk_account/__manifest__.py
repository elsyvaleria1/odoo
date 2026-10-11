{
    "name": "Helpdesk Credit Notes",
    "category": "Services/Helpdesk",
    "summary": "Create and access credit notes from helpdesk tickets",
    "description": "Adds ticket links to credit notes and adapts the invoice-reversal wizard to select invoices and sales orders for a ticket. Accounting access and an invoice eligible for reversal are required.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "helpdesk_sale",
        "account",
    ],
    "data": [
        "data/mail_message_subtype_data.xml",
        "wizards/account_move_reversal_views.xml",
        "views/account_move_views.xml",
        "views/helpdesk_ticket_views.xml",
    ],
    "demo": [
        "demo/helpdesk_account_demo.xml",
    ],
}
