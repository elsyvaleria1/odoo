{
    "name": "SAF-T Export Foundation",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Provide shared accounting export structures for SAF-T localizations",
    "description": "Prepare general-ledger account and entry values for SAF-T reports. Country-specific modules supply their required XML layouts and export details.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "data/saft_report.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_saft/static/src/components/**/*",
        ],
    },
}
