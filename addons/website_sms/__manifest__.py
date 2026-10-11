{
    "name": "Website Visitor Contact SMS",
    "version": "1.0",
    "category": "Website/Website",
    "sequence": 54,
    "summary": "Open an SMS composer for a visitor linked to a contact with phone numbers",
    "description": "Adds a visitor action that checks the linked contact for phone records and opens the SMS composer for that contact. Requires a usable destination number and SMS service configuration; anonymous visits alone provide no phone number.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website",
        "sms",
    ],
    "data": [
        "views/website_visitor_views.xml",
    ],
    "auto_install": True,
}
