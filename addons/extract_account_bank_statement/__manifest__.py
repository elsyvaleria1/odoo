{
    "name": "Bank Statement Document Extraction",
    "version": "19.0.1.0.0",
    "category": "Accounting/Accounting",
    "summary": "Extract balances and transactions from attached bank statement documents",
    "description": "Maps opening and declared closing balances and period end into a bank statement, creating transactions only when it has no lines. Adds PDF and image import handling that queues extraction and rejects mixed scanned and other file types in one batch. Requires a suitable extraction reader or strategy for the source document; extracted amounts remain subject to statement consistency checks.",
    "author": "AgroMarin",
    "website": "https://agromarin.com",
    "license": "OEEL-1",
    "depends": [
        "account_bank_statement_import",
        "extract",
    ],
    "data": [
        "views/account_bank_statement_views.xml",
    ],
}
