{
    "name": "Cash-Basis Report Calculations",
    "category": "Accounting/Accounting",
    "summary": "Add an optional cash-basis calculation mode to accounting reports",
    "description": "Adds a configurable cash-basis report filter and computes report queries through temporary journal-item tables using payment and reconciliation data. Supports report labels and drill-down adaptations; the filter must be enabled on the report and selected in its options.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "account",
    ],
    "data": [
        "data/account_reports_data.xml",
        "views/account_report_view.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "account_reports_cash_basis/static/src/components/**/*",
        ],
        "web.assets_unit_tests": [
            "account_reports_cash_basis/static/tests/**/*.js",
        ],
    },
}
