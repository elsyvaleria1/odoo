{
    "name": "Reseller Lead Map Fields",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Display reseller assignment in enterprise CRM views",
    "description": "Extends the CRM lead views with the reseller-assignment fields supplied by the partner assignment integration.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "crm_enterprise",
        "website_crm_partner_assign",
    ],
    "data": [
        "views/crm_lead_views.xml",
    ],
    "auto_install": True,
}
