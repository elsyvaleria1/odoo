{
    "name": "Salary Offer Time Off",
    "category": "Human Resources",
    "summary": "Create extra time-off allocations from signed salary offers",
    "description": "Extends salary-offer signature processing with the configured extra leave allocation.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_contract_salary",
        "hr_holidays",
    ],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "auto_install": True,
}
