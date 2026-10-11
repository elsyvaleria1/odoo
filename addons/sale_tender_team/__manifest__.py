{
    "name": "Sales Tender Team Access",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Enable sales tender access for sales-team roles",
    "description": "Supplies access-control entries linking sales tender records with the sales-team roles declared by its dependencies.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_tender",
        "sale_team",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "auto_install": True,
}
