{
    "name": "Visitor Lead Map Fields",
    "version": "1.0",
    "category": "Sales/CRM",
    "summary": "Display website visitor lead data in enterprise CRM views",
    "description": "Extends CRM lead views with information supplied by website visitor identification and lead generation.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "crm_enterprise",
        "website_crm_iap_reveal",
    ],
    "data": [
        "views/crm_lead_views.xml",
    ],
    "auto_install": True,
}
