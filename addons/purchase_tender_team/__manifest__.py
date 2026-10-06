{
    "name": "Purchase Tender Team Access",
    "version": "1.0",
    "category": "Supply Chain/Purchase",
    "summary": "Enable purchase tender access for purchasing teams",
    "description": "Supplies access-control entries for purchase tenders when the purchasing team integration is installed.",
    "author": "AgroMarin",
    "license": "LGPL-3",
    "depends": [
        "purchase_tender",
        "purchase_team",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "auto_install": True,
}
