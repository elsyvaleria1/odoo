{
    "name": "Rental Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Rental spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Rental. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "spreadsheet_dashboard",
        "sale_renting",
    ],
    "data": [
        "data/dashboards.xml",
    ],
    "auto_install": [
        "sale_renting",
    ],
}
