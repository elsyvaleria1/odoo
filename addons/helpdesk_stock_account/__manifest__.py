{
    "name": "Helpdesk Product Refunds",
    "category": "Services/Helpdesk",
    "summary": "Select products and lots when preparing helpdesk invoice refunds",
    "description": "Extends the invoice reversal wizard with product, lot and suitable-order filters for helpdesk stock and accounting flows.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "helpdesk_stock",
        "helpdesk_account",
    ],
    "data": [
        "wizards/wizard_account_move_reverse_views.xml",
    ],
    "auto_install": True,
}
