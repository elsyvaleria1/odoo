{
    "name": "Project Manufacturing Costs",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Include manufacturing analytic costs in project profitability",
    "description": "Propagates project analytic accounts into manufacturing moves and work-order entries and reports their costs in project profitability.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mrp_account",
        "project_mrp",
    ],
    "demo": [
        "demo/project_mrp_account_demo.xml",
    ],
    "auto_install": True,
}
