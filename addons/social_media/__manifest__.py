{
    "name": "Company Social Account Links",
    "version": "0.2",
    "oldest_upgradable_version": "0.2",
    "category": "Marketing/Social Marketing",
    "summary": "Store company social account links for use by other addons",
    "description": "Adds per-company configuration fields for social account URLs and the company configuration relation. Consumer addons choose where to display or use these links; this module supplies no social network authentication, posting or synchronization client.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "base",
    ],
    "data": [
        "security/ir.access.csv",
        "views/res_company_views.xml",
    ],
    "demo": [
        "demo/res_company_demo.xml",
    ],
}
