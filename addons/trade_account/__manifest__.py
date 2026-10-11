{
    "name": "Trade Accounting Infrastructure",
    "version": "19.0.1.1.0",
    "category": "Hidden",
    "summary": "Share order invoicing, down-payment and accounting-match helpers",
    "description": "Provides abstract invoice-status and quantity calculations, order-to-invoice creation helpers, document import and matching report models. Extends accounting moves and lines with common order-link behavior. Concrete sales and purchase integrations supply their order types and business actions; the infrastructure has no standalone order application.",
    "author": "Odoo Community",
    "website": "https://www.odoo.com",
    "license": "Other OSI approved licence",
    "depends": [
        "trade",
        "account",
    ],
    "data": [
        "security/res_groups.xml",
    ],
}
