{
    "name": "SAF-T Accounting Import",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Localizations/Reporting",
    "summary": "Import supported SAF-T account, partner, tax and transaction records",
    "description": "Adds a SAF-T XML import wizard that maps accounts, partners, taxes, journals and entries and can prepare opening-balance adjustments. Country extensions adapt specific layouts; the importer does not claim to support every national SAF-T variant.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account_saft",
        "account_base_import",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/import_wizard_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_saft_import/static/src/xml/**/*",
        ],
    },
}
