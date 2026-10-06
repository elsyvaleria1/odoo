{
    "name": "Postal Invoice Delivery",
    "version": "0.1",
    "category": "Hidden/Tools",
    "summary": "Send invoices through the postal document delivery service",
    "description": "Add postal letters to invoice sending options and prepare their recipients and attachments. Uses the postal service provided by the letter-delivery dependency.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "account",
        "snailmail",
    ],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "auto_install": True,
}
