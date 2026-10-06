{
    "name": "Trade Account Tests",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tests",
    "summary": "Test Trade Account behaviour, including document match, invoice, invoice state",
    "description": "Run regression tests for Trade Account. Loaded test suites include ``TestDocumentMatch``, ``TestInvoice``, ``TestInvoiceState``, ``TestLineMatch``, ``TestOrderAmounts``.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "test_trade",
        "trade_account",
        "sale",
        "purchase",
    ],
    "data": [
        "security/ir.access.csv",
    ],
}
