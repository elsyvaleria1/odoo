{
    "name": "Trade Tests",
    "version": "19.0.1.3.0",
    "oldest_upgradable_version": "19.0.1.1.0",
    "category": "Hidden/Tests",
    "summary": "Test Trade behaviour, including catalog, confirm validation, duplicates",
    "description": "Run regression tests for Trade. Loaded test suites include ``TestCatalog``, ``TestConfirmValidation``, ``TestDuplicateOrders``, ``TestHeaderMisc``, ``TestLineAmounts``.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "trade",
    ],
    "data": [
        "security/ir.access.csv",
        "data/test_trade_order_data.xml",
        "data/test_trade_order_action.xml",
    ],
}
