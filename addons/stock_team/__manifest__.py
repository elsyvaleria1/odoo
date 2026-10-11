{
    "name": "Inventory Teams",
    "version": "1.1",
    "category": "Supply Chain/Inventory",
    "summary": "Assign stock transfers to operational teams",
    "description": "Adds team usage, assignment fields and views for stock transfers, with team-specific access rules and navigation.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "stock",
        "team",
    ],
    "data": [
        "security/stock_team_security.xml",
        "security/ir.access.csv",
        "security/ir_access.xml",
        "views/team_team_views.xml",
        "views/stock_picking_views.xml",
        "views/stock_team_menus.xml",
    ],
    "auto_install": True,
}
