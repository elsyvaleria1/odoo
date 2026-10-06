{
    "name": "Intercompany Invoice Counterparts",
    "version": "1.1",
    "category": "Productivity",
    "summary": "Create vendor bills and refunds from posted intercompany sales invoices and credit notes",
    "description": "Generates counterpart vendor documents when a posted sales document targets another configured company with bill generation enabled. Uses the receiving company user, journal and document-state settings, with optional automatic posting and origin links to avoid duplicate mirrors. This flow does not generate customer invoices from vendor bills.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account",
    ],
    "data": [
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
    ],
}
