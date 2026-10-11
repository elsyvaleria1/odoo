{
    "name": "Journal Item Tax Grid Updates",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Accounting",
    "summary": "Update existing journal item tax tags from current tax configuration",
    "description": "Adds a wizard under accounting settings in developer mode to rebuild tax-tag links for the selected company from a starting date. Uses the current tax repartition configuration and rejects child taxes shared by multiple parent taxes; review the period and configuration before applying it.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.access.csv",
        "views/res_config_settings_views.xml",
        "wizards/wizard_account_move_line_update_tax_tag_views.xml",
    ],
}
