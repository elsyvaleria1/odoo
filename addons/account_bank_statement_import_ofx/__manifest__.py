{
    "name": "OFX Bank Statement Import",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Import bank transactions from OFX statement files",
    "description": "Add OFX parsing to the bank statement import flow and convert transactions into bank statement lines. Uses the common statement importer for bank-account matching and record creation.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account_bank_statement_import",
    ],
    "external_dependencies": {
        "python": [
            "ofxparse",
        ],
    },
    "auto_install": True,
}
