{
    "name": "Vendor Bill Purchase Order Matching from Extraction",
    "version": "19.0.1.0.0",
    "category": "Accounting",
    "summary": "Match extracted purchase references to orders for vendor bills without lines",
    "description": "Extends the invoice extraction schema with a purchase-order reference and passes extracted reference tokens, partner and total to the accounting purchase-matching routine. Runs only for vendor bills without invoice lines after extraction updates; matching behavior comes from the purchase dependency.",
    "author": "AgroMarin",
    "website": "https://agromarin.com",
    "license": "Other OSI approved licence",
    "depends": [
        "extract_account",
        "purchase",
    ],
}
