{
    "name": "Subscription Spreadsheet Dashboards",
    "category": "Productivity/Dashboard",
    "summary": "Add Subscriptions, MRR Evolution, Retention, Salesperson spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Subscriptions, MRR Evolution, Retention, Salesperson. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "spreadsheet_dashboard",
        "sale_subscription",
    ],
    "data": [
        "data/dashboards.xml",
        "views/sale_subscription_report_views.xml",
    ],
    "auto_install": [
        "sale_subscription",
    ],
}
