{
    "name": "Website Visitor Lead SMS",
    "version": "1.0",
    "category": "Website/Website",
    "sequence": 54,
    "summary": "Open SMS composition through a matching lead when a visitor lacks a usable contact",
    "description": "Extends visitor SMS eligibility to leads whose recorded phone numbers match the visitor mobile number. When no contact is linked, it selects the matching lead with the highest confidence for the composer; sending uses the SMS dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website_sms",
        "crm",
    ],
    "auto_install": True,
}
