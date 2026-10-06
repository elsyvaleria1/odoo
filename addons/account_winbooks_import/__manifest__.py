{
    "name": "Winbooks Accounting Import",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Accounting",
    "summary": "Import supported Winbooks accounting exports",
    "description": "Reads exported Winbooks files from an uploaded archive and imports partners, accounts, journals, entries and analytic data. Provides import options and a result summary.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account",
        "account_vat",
        "account_base_import",
    ],
    "external_dependencies": {
        "python": [
            "dbfread",
        ],
        "apt": {
            "dbfread": "python3-dbfread",
        },
    },
    "data": [
        "security/ir.access.csv",
        "wizards/wizard_account_import_summary_views.xml",
        "wizards/wizard_account_move_import_winbooks_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_winbooks_import/static/src/xml/**/*",
        ],
    },
}
