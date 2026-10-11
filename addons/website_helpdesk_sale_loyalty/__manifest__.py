{
    "name": "Helpdesk Coupon Share Links",
    "version": "1.0",
    "category": "Services/Helpdesk",
    "summary": "Generate a ticket-linked coupon and open its website sharing action",
    "description": "Extends the ticket coupon wizard to create a loyalty card for the ticket contact using the selected program, points and expiry date, then opens the program share action. Requires an applicable website loyalty program; redemption is handled by the dependencies.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sale_loyalty",
        "helpdesk_sale_loyalty",
    ],
    "data": [
        "wizards/wizard_helpdesk_ticket_create_coupon_views.xml",
    ],
    "auto_install": True,
}
