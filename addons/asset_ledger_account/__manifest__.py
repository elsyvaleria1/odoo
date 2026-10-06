{
    "name": "Asset Ledger Bill Links",
    "version": "19.0.1.7.0",
    "oldest_upgradable_version": "19.0.1.5.0",
    "category": "Accounting/Accounting",
    "summary": "Open asset bill lines from serialized stock lots",
    "description": "Relates journal items to their asset stock lot and exposes bill navigation from the lot. Asset log views link to the associated journal entry and make billed amounts read-only.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "asset_ledger",
        "resource_asset_account",
    ],
    "data": [
        "views/product_asset_log_views.xml",
    ],
    "demo": [
        "demo/account_move_demo.xml",
        "demo/account_move_line_demo.xml",
    ],
}
