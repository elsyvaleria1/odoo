{
    "name": "Manufacturing Subcontracting Cost Analysis",
    "version": "1.0",
    "category": "Supply Chain/Manufacturing",
    "summary": "Include subcontracting costs in manufacturing cost analysis",
    "description": "Extends the manufacturing report with total and per-unit subcontracting costs derived from linked subcontracting stock moves. Includes these amounts in reported total production cost, with report currency conversion and byproduct cost allocation for the per-unit measure.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/manufacturing",
    "license": "OEEL-1",
    "depends": [
        "mrp_account_enterprise",
        "mrp_subcontracting",
    ],
    "data": [
        "reports/mrp_report_views.xml",
    ],
    "auto_install": True,
}
