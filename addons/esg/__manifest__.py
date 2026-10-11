{
    "name": "Carbon Emissions Accounting",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "ESG",
    "summary": "Estimate carbon emissions from accounting entries and recorded activities",
    "description": "Applies configured emission factors to accounting lines and other activity records, tracks uncertainty and presents carbon reports by source and scope. Estimates depend on the supplied quantities, factors and classifications.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
        "web_hierarchy",
    ],
    "external_dependencies": {
        "python": [
            "openpyxl",
        ],
        "apt": {
            "openpyxl": "python3-openpyxl",
        },
    },
    "data": [
        "security/esg_security.xml",
        "security/ir.access.csv",
        "data/esg_database_data.xml",
        "data/esg_emission_source_data.xml",
        "data/esg_gas_data.xml",
        "data/carbon_report.xml",
        "reports/esg_carbon_emission_report_views.xml",
        "wizards/wizard_esg_emission_factor_apply_move_line_views.xml",
        "views/account_move_views.xml",
        "views/esg_emission_factor_views.xml",
        "views/esg_emission_source_views.xml",
        "views/esg_gas_views.xml",
        "views/esg_database_views.xml",
        "views/esg_other_emission_views.xml",
        "views/esg_menus.xml",
    ],
    "demo": [
        "demo/demo_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "esg/static/src/**/*",
        ],
        "web.assets_web_dark": [],
        "web.assets_unit_tests": [
            "esg/static/tests/esg_models.js",
            "esg/static/tests/**/*.test.js",
        ],
    },
    "application": True,
}
