{
    "name": "CRM Sales Challenges",
    "version": "1.0",
    "category": "Sales/CRM",
    "summary": "Provide CRM goal definitions and sales challenges",
    "description": "Load goal and challenge definitions for CRM and sales activity. Uses the generic gamification engine to evaluate the configured objectives.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "gamification",
        "sale_crm",
    ],
    "data": [
        "data/gamification_sale_crm_data.xml",
    ],
    "demo": [
        "demo/gamification_sale_crm_demo.xml",
    ],
    "auto_install": True,
}
