{
    "name": "CRM SMS Composer",
    "version": "1.1",
    "category": "Sales/CRM",
    "summary": "Compose text messages from lead forms",
    "description": "Adds the SMS composer action to CRM lead views. Sending uses the configured SMS service.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "crm",
        "sms",
    ],
    "data": [
        "views/crm_lead_views.xml",
        "security/ir.access.csv",
    ],
    "auto_install": True,
}
