{
    "name": "Vehicle Fiscal Categories",
    "version": "2.0",
    "oldest_upgradable_version": "2.0",
    "category": "Accounting/Accounting",
    "summary": "Report vehicle costs using vehicle-specific deduction rates",
    "description": "Adds vehicle rate history and vehicle grouping to the fiscal category report. Extends deferred-entry preparation with the associated asset.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account_accountant_fleet",
        "account_fiscal_categories",
    ],
    "data": [
        "security/ir.access.csv",
        "data/account_fiscal_report.xml",
        "views/account_fiscal_category_views.xml",
        "views/fleet_vehicle_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_fiscal_categories_fleet/static/src/components/**/*",
        ],
    },
    "auto_install": True,
}
