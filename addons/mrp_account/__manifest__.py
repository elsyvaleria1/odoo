{
    "name": "Manufacturing Accounting",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Supply Chain/Manufacturing",
    "summary": "Analytic accounting in Manufacturing",
    "description": """
Analytic Accounting in MRP
==========================

* Cost structure report

Also, allows to compute the cost of the product based on its BoM, using the costs of its components and work center operations.
It adds a button on the product itself but also an action in the list view of the products.
If the automated inventory valuation is active, the necessary accounting entries will be created.

""",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/manufacturing",
    "license": "LGPL-3",
    "depends": [
        "mrp",
        "stock_account",
    ],
    "data": [
        "security/ir.access.csv",
        "views/product_views.xml",
        "views/mrp_production_views.xml",
        "views/analytic_account_views.xml",
        "views/account_move_views.xml",
        "views/mrp_workcenter_views.xml",
        "reports/report_mrp_templates.xml",
        "reports/stock_valuation_report.xml",
        "wizards/wizard_mrp_production_post_wip_entry_views.xml",
    ],
    "demo": [
        "demo/mrp_account_demo.xml",
    ],
    "auto_install": True,
    "post_init_hook": "_configure_journals",
}
