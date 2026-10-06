{
    "name": "Manufacturing Traceability Demo Data",
    "version": "1.0",
    "category": "Supply Chain/Manufacturing",
    "sequence": 50,
    "summary": "Load sample purchasing and quality records for manufacturing traceability",
    "description": "Supplies demonstration records connecting purchasing, manufacturing work orders and quality checks. The records are loaded only when demo data is enabled.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "purchase_mrp",
        "quality_mrp_workorder",
        "purchase_stock",
    ],
    "demo": [
        "demo/purchase_mrp_workorder_quality_demo.xml",
    ],
    "auto_install": True,
}
