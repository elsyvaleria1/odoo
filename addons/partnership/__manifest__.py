{
    "name": "Memberships and Partnerships",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/CRM",
    "summary": "Assign membership grades and track partner memberships",
    "description": "Configure partner grades and manage membership assignment and confirmation. The module links membership records to the contacts they concern.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "crm",
        "sale",
    ],
    "data": [
        "security/ir.access.csv",
        "data/res_partner_grade_data.xml",
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
        "views/res_partner_grade_views.xml",
        "views/product_template_views.xml",
        "views/product_pricelist_views.xml",
        "views/partnership_menu.xml",
    ],
}
