{
    "name": "CRM Lead Mining",
    "version": "1.2",
    "category": "Sales/CRM",
    "summary": "Request leads from the IAP service using company and contact filters",
    "description": "Provides requests filtered by geography, industry, company size and contact roles. Converts returned results into leads and tracks the request cost and state; service credits are required.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "iap_crm",
        "iap_mail",
    ],
    "data": [
        "data/crm.iap.lead.industry.csv",
        "data/crm.iap.lead.role.csv",
        "data/crm.iap.lead.seniority.csv",
        "data/mail_template_data.xml",
        "data/ir_sequence_data.xml",
        "security/ir.access.csv",
        "views/crm_lead_views.xml",
        "views/crm_iap_lead_mining_request_views.xml",
        "views/res_config_settings_views.xml",
        "views/mail_templates.xml",
        "views/crm_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "crm_iap_mine/static/src/js/**/*",
        ],
    },
    "auto_install": True,
}
