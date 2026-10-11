{
    "name": "EMV Payment QR Codes",
    "version": "1.0",
    "category": "Accounting/Payment",
    "summary": "Generate merchant-presented EMV payment QR payloads",
    "description": "Provide EMV field serialization, checksums and QR rendering support. Country-specific payment integrations supply merchant account and proxy details.",
    "author": "Odoo SA",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "data": [
        "views/res_bank_views.xml",
    ],
}
