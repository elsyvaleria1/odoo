{
    "name": "Website Sales Analysis Views",
    "version": "1.0",
    "category": "Website/Website",
    "sequence": 55,
    "summary": "Open sales graphs and pivots for teams associated with websites",
    "description": "Adds sales-analysis graph and pivot views, search filters and a website dashboard redirect for sales users. The action selects sales report rows whose team has a website and defaults to confirmed orders; it does not independently prove that every included order originated online.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "website_sale",
    ],
    "data": [
        "views/dashboard_view.xml",
    ],
    "auto_install": [
        "website_sale",
    ],
}
