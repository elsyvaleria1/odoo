{
    "name": "Employee Commuting Emissions",
    "version": "2.1",
    "oldest_upgradable_version": "2.1",
    "category": "ESG",
    "summary": "Estimate commuting emissions from employee vehicle data",
    "description": "Calculates commuting distance and CO2 using vehicle assignments and configured days at the office. A wizard records estimates as emissions and checks for overlapping entries.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "esg",
        "hr_fleet",
    ],
    "data": [
        "data/esg_hr_fleet_data.xml",
        "security/ir.access.csv",
        "reports/esg_employee_commuting_report_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_esg_other_emission_create_commuting_views.xml",
        "views/esg_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "esg_hr_fleet/static/src/**/*",
        ],
    },
    "auto_install": True,
}
