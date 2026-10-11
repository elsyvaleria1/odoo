{
    "name": "Manufacturing Asset Maintenance Menu",
    "version": "19.0.1.0.0",
    "category": "Supply Chain/Maintenance",
    "summary": "Open machinery assets, maintenance plans and orders from Manufacturing",
    "description": "Adds a Maintenance submenu under Manufacturing with links to machinery assets, maintenance plans and maintenance orders. The actions and maintenance behavior are implemented by Asset Ledger Maintenance; this addon contributes menu records only.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "asset_ledger_maintenance",
        "mrp",
    ],
    "data": [
        "views/menuitem_views.xml",
    ],
    "auto_install": True,
}
