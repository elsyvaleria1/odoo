{
    "name": "Warehouse Intrastat Data",
    "category": "Supply Chain/Inventory",
    "summary": "Use warehouse information when preparing Intrastat reports",
    "description": "Add Intrastat settings to warehouses and use stock information to fill report values. Extends the generic Intrastat report handler.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "stock_account",
        "account_intrastat",
    ],
    "data": [
        "views/stock_warehouse_view.xml",
    ],
    "auto_install": True,
}
