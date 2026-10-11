{
    "name": "CRM Lead Enrichment",
    "version": "1.1",
    "category": "Sales/CRM",
    "summary": "Enrich leads with company information from the IAP service",
    "description": "Adds manual and scheduled enrichment of leads and writes company information returned by the service. Requires service access and available credits; enrichment depends on a matching company.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "iap_crm",
        "iap_mail",
    ],
    "data": [
        "data/ir_cron.xml",
        "data/ir_action.xml",
        "data/mail_templates.xml",
        "views/crm_lead_views.xml",
        "views/res_config_settings_view.xml",
    ],
    "auto_install": True,
    "post_init_hook": "_sync_cron",
}
