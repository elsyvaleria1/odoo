{
    "name": "Mailbox Plugin Integration",
    "version": "1.0",
    "category": "Sales/CRM",
    "sequence": 5,
    "summary": "Expose contact lookup and email logging to authenticated mailbox plugins",
    "description": "Adds plugin authorization, contact search and creation, optional contact enrichment and email-content logging routes. Requires a compatible mailbox plugin and scoped credentials. Base logging accepts contact records; extension addons add other target models, while enrichment depends on the external IAP service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
        "partner",
        "iap",
    ],
    "data": [
        "data/res_users_apikeys_scope_data.xml",
        "views/mail_plugin_login.xml",
        "views/res_partner_iap_views.xml",
        "security/ir.access.csv",
        "views/mail_plugin_menus.xml",
    ],
}
