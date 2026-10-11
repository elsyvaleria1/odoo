{
    "name": "Payroll Accounting",
    "category": "Human Resources/Payroll",
    "summary": "Create journal entries from completed employee payslips",
    "description": "Map payroll structures and salary rules to accounting journals and accounts. Generates payslip journal entries and links them to payroll records.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_payroll",
        "accountant",
        "account_iban",
    ],
    "data": [
        "data/hr_salary_rule_data.xml",
        "views/hr_payslip_run_views.xml",
        "views/hr_payslip_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_contract_template_views.xml",
        "views/hr_salary_rule_views.xml",
        "views/hr_payroll_structure_views.xml",
        "views/res_config_settings_views.xml",
        "views/account_move_views.xml",
        "views/res_partner_bank_account_views.xml",
    ],
    "demo": [
        "demo/hr_payroll_account_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_payroll_account/static/src/**/*",
        ],
        "web.assets_tests": [
            "hr_payroll_account/static/tests/tours/**/*",
        ],
    },
    "auto_install": [
        "hr_payroll",
        "accountant",
    ],
    "pre_init_hook": "_salaries_account_journal_pre_init",
    "post_init_hook": "_hr_payroll_account_post_init",
}
