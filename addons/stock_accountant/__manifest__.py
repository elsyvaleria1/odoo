{
    "name": "Inventory Valuation Report Settings",
    "version": "1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Configure valuation accounts and open inventory valuation reports",
    "description": "Adds accounting settings for inventory valuation and the associated valuation-report definitions.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_account",
        "account",
    ],
    "data": [
        "views/res_config_settings_views.xml",
        "views/stock_accountant_menus.xml",
    ],
    "auto_install": True,
}
