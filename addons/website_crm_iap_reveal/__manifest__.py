{
    "name": "Website Visitor Lead Generation",
    "version": "1.1",
    "category": "Sales/CRM",
    "summary": "Create leads from companies identified among website visitors",
    "description": "Requests company identification for website visits and applies configured lead-generation rules to returned matches. Requires service access and credits; anonymous visits do not necessarily resolve to a company.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "iap_crm",
        "iap_mail",
        "crm_iap_mine",
        "website_crm",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "data/ir_model_data.xml",
        "security/ir.access.csv",
        "views/crm_lead_views.xml",
        "views/crm_reveal_views.xml",
        "views/res_config_settings_views.xml",
        "views/crm_menus.xml",
    ],
}
