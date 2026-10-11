{
    "name": "Product Invoice Emails",
    "category": "Accounting/Accounting",
    "summary": "Send product-specific email templates when posting invoices",
    "description": "Associate products with email templates and use them in the invoice posting flow. Generates product-related messages from the posted invoice information.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "views/product_views.xml",
        "views/mail_template_views.xml",
    ],
}
