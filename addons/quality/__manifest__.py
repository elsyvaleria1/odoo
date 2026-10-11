{
    "name": "Quality Check and Alert Infrastructure",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Supply Chain/Quality",
    "sequence": 50,
    "summary": "Define quality points, checks, teams and staged alerts",
    "description": "Provides quality control-point definitions, check records with pass or fail actions, sampling rules and alert stages. Quality execution interfaces, measurement-specific fields and manufacturing integration are supplied by extension modules; this addon defines the shared records and configuration.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "stock",
        "team",
    ],
    "data": [
        "security/quality.xml",
        "security/ir.access.csv",
        "data/quality_data.xml",
        "views/quality_views.xml",
    ],
}
