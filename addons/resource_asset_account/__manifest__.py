{
    "name": "Asset Accounting and Costs",
    "version": "1.3",
    "oldest_upgradable_version": "1.2",
    "category": "Hidden",
    "summary": "Link bill and analytic lines to assets and their cost history",
    "description": "Adds asset references to accounting lines, derives asset logs from bills and links installed parts to their bill lines. Flagged part reviews can hold related bill payments.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
        "resource_asset_product",
    ],
    "data": [
        "security/ir_access_class.xml",
        "views/account_account_views.xml",
        "views/account_move_views.xml",
        "views/account_analytic_line_views.xml",
        "views/resource_asset_views.xml",
    ],
    "auto_install": True,
}
