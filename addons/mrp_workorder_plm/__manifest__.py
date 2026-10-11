{
    "name": "Work Order Engineering Changes",
    "version": "1.0",
    "category": "Supply Chain/Product Lifecycle Management (PLM)",
    "summary": "Track work-order instruction and quality-point changes in engineering revisions",
    "description": "Links work-order instructions and quality steps with engineering change orders and revision bills of materials.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mrp_workorder",
        "mrp_plm",
    ],
    "data": [
        "views/mrp_eco_views.xml",
    ],
    "auto_install": True,
}
