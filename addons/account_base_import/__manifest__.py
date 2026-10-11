{
    "name": "Accounting Import Setup",
    "version": "1.1",
    "category": "Accounting/Accounting",
    "summary": "Import accounting records with journal-item grouping and setup summaries",
    "description": "Adds accounting import entry points, setup views and import summaries. Account loading can match existing accounts, and journal-item loading separates move headers from lines before creating entries; imported data still needs appropriate accounts, journals and mappings.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
        "base_import",
        "account_depreciation",
    ],
    "data": [
        "security/ir.access.csv",
        "views/account_import_views.xml",
        "views/account_account_views.xml",
        "views/account_move_views.xml",
        "views/res_partner_views.xml",
        "views/account_asset_views.xml",
        "wizards/wizard_account_import_summary_views.xml",
        "wizards/setup_wizards_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_base_import/static/src/js/**/*",
            "account_base_import/static/src/xml/**/*",
        ],
    },
    "auto_install": True,
}
