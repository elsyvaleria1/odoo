{
    "name": "Vehicle Depreciation Costs",
    "version": "2.0",
    "oldest_upgradable_version": "2.0",
    "category": "Accounting/Accounting",
    "summary": "Include depreciation entries in vehicle asset costs",
    "description": "Extends depreciation move preparation and asset-log amount calculation when fleet assets carry depreciation boards.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account_fleet",
        "resource_asset_account",
        "account_depreciation",
    ],
    "data": [
        "views/account_asset_views.xml",
        "views/account_move_views.xml",
    ],
    "auto_install": True,
}
