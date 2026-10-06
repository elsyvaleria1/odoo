{
    "name": "Asset Fuel and Toll Wallets",
    "version": "19.0.1.2.0",
    "oldest_upgradable_version": "19.0.1.2.0",
    "category": "Accounting/Accounting",
    "summary": "Track fuel and toll wallet cards against assets",
    "description": "Links wallet cards and transactions to assets and stock lots. Asset views show associated cards, budgets, balances and amounts to reload.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "wallet_reorder",
        "asset_ledger",
    ],
    "data": [
        "views/wallet_card_views.xml",
        "views/resource_asset_views.xml",
    ],
    "auto_install": True,
}
