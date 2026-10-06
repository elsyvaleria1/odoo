{
    "name": "CRM Mail Plugin Actions",
    "version": "1.0",
    "category": "Sales/CRM",
    "sequence": 5,
    "summary": "Create and open CRM leads from the mail-client plugin",
    "description": "Adds plugin endpoints for contact leads, lead creation and logging email content. Requires the mail-client plugin integration provided by its dependency.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/crm",
    "license": "LGPL-3",
    "depends": [
        "crm",
        "mail_plugin",
    ],
    "data": [
        "views/crm_mail_plugin_lead.xml",
        "views/crm_lead_views.xml",
    ],
    "auto_install": True,
}
