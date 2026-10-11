{
    "name": "Helpdesk Coupons and Gift Cards",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Services/Helpdesk",
    "summary": "Generate coupons and gift cards linked to helpdesk tickets",
    "description": "Adds ticket actions and wizards for issuing loyalty cards, coupon values and validity dates. Requires an applicable loyalty program; generated cards remain linked to the originating ticket.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "helpdesk_sale",
        "sale_loyalty",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/wizard_helpdesk_ticket_create_coupon_views.xml",
        "wizards/wizard_loyalty_program_create_card_views.xml",
        "views/helpdesk_ticket_views.xml",
        "views/loyalty_card_views.xml",
    ],
    "demo": [
        "demo/helpdesk_sale_coupon_demo.xml",
    ],
}
