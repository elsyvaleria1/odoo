{
    "name": "Field Service Repair Transfer Access",
    "version": "1.0",
    "category": "Services/Field Service",
    "summary": "Open field-service stock references without repair-management access",
    "description": "Adds field-service access rules and a stock-reference action that avoids opening repair records for users without repair permissions.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "industry_fsm_stock",
        "repair",
    ],
    "data": [
        "security/ir.access.csv",
        "views/stock_picking_views.xml",
    ],
    "auto_install": True,
}
