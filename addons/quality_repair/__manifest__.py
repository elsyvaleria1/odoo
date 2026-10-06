{
    "name": "Repair Quality Checks",
    "version": "1.0",
    "category": "Supply Chain/Quality",
    "sequence": 50,
    "summary": "Create and track quality checks and alerts on repair orders",
    "description": "Links checks and alerts to repairs and creates checks from applicable quality control points during repair processing. Check selection depends on the repair product and operation type; completing checks records inspection outcomes rather than guaranteeing repaired-product quality.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "quality_control",
        "repair",
    ],
    "data": [
        "views/quality_views.xml",
        "views/repair_views.xml",
    ],
    "auto_install": True,
}
