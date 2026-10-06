{
    "name": "Purchase Teams",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Supply Chain/Purchase",
    "summary": "Assign purchase orders to operational teams",
    "description": "Adds team usage, assignment fields and views for purchase orders, with team-specific access rules and navigation.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "purchase",
        "team",
    ],
    "data": [
        "security/purchase_team_security.xml",
        "security/ir.access.csv",
        "views/team_team_views.xml",
        "views/purchase_order_views.xml",
        "views/purchase_team_menus.xml",
    ],
    "auto_install": True,
}
