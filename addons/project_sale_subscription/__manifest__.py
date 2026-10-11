{
    "name": "Project Subscription Links",
    "version": "1.0",
    "category": "Services/Project",
    "summary": "Connect subscription sales items, generated project work and project profitability",
    "description": "Adds subscription navigation from analytic accounts and projects, subscription items in project profitability, and adaptations to service and recurring-task generation. Requires eligible subscription sales items and project service configuration; recurring billing remains in the subscription dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_project",
        "sale_subscription",
    ],
    "data": [
        "views/account_analytic_account_views.xml",
        "views/sale_order_line_views.xml",
        "views/sale_order_views.xml",
    ],
    "demo": [
        "demo/product_product_demo.xml",
        "demo/project_task_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "project_sale_subscription/static/src/components/project_right_side_panel/**/*",
        ],
    },
    "auto_install": True,
}
