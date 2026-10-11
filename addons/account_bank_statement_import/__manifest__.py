{
    "name": "Bank Statement Import",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Import bank statements through format-specific parsers",
    "description": "Provide statement upload, validation and bank-account setup handling. File-format support is supplied by separate parser modules.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
        "base_import",
    ],
    "data": [
        "views/account_bank_statement_import_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_bank_statement_import/static/src/**/*",
        ],
    },
    "auto_install": True,
}
