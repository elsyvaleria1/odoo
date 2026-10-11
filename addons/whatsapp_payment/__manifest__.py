{
    "name": "Whatsapp-Payment",
    "category": "Productivity/WhatsApp",
    "summary": "Send payment links through WhatsApp",
    "description": "Add a WhatsApp sending action to the payment-link wizard. Uses the payment-link message template and the configured WhatsApp account.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "payment",
        "whatsapp",
    ],
    "data": [
        "data/whatsapp_template_data.xml",
        "wizards/wizard_payment_transaction_view_link_views.xml",
    ],
    "auto_install": True,
}
