{
    "name": "Manufacturing Valuation Account Settings",
    "version": "1.0",
    "category": "Supply Chain/Inventory",
    "summary": "Configure manufacturing work-in-progress and overhead accounts",
    "description": "Adds manufacturing account fields to the inventory valuation settings view. The manufacturing accounting implementation is supplied by its dependency.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "mrp_account",
        "stock_accountant",
    ],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "auto_install": True,
}
