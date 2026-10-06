{
    "name": "CRM Rental Quotations",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Sales",
    "summary": "Create rental quotations from CRM opportunities",
    "description": "Add rental quotation actions and counts to opportunities. A creation wizard links the generated rental order to the opportunity.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sale_renting",
        "sale_crm",
    ],
    "data": [
        "security/ir.access.csv",
        "views/crm_lead_views.xml",
        "wizards/wizard_crm_lead_create_rental_quotation_views.xml",
    ],
    "auto_install": True,
}
