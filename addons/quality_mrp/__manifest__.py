{
    "name": "Manufacturing Quality Checks",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Supply Chain/Quality",
    "sequence": 50,
    "summary": "Create and process quality checks for manufacturing orders",
    "description": "Add quality control points, checks and alerts to manufacturing orders and their stock movements. Production workflows check the applicable quality results before completion.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "quality_control",
        "mrp",
    ],
    "data": [
        "security/quality_mrp.xml",
        "security/ir.access.csv",
        "views/quality_views.xml",
        "views/mrp_production_views.xml",
        "reports/worksheet_custom_report_templates.xml",
    ],
    "auto_install": True,
}
