{
    "name": "Manufacturing Employee Costs",
    "category": "Supply Chain/Manufacturing",
    "summary": "Record employee work-order costs as analytic entries",
    "description": "Creates employee-linked analytic costs for work orders and adds expected and actual employee costs to manufacturing reports.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mrp_workorder",
        "mrp_account_enterprise",
    ],
    "data": [
        "reports/mrp_report_views.xml",
    ],
    "auto_install": True,
}
