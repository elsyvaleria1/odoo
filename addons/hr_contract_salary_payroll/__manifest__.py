{
    "name": "Salary Offer Payroll Simulation",
    "category": "Human Resources",
    "summary": "Calculate payroll results for salary-offer simulations",
    "description": "Connects the salary configurator with payslip calculations and exposes calculated payroll results in the offer. Results depend on configured payroll structures and rules.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_contract_salary",
        "hr_payroll",
    ],
    "data": [
        "data/hr_contract_salary_resume_data.xml",
        "data/ir_cron_data.xml",
        "views/hr_contract_salary_offer_views.xml",
        "views/menuitems.xml",
        "views/hr_contract_salary_resume_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_contract_salary_template.xml",
        "views/hr_payroll_headcount.xml",
        "views/hr_contract_salary_benefit_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "hr_contract_salary_payroll/static/src/js/*.js",
            "hr_contract_salary_payroll/static/src/xml/*.xml",
        ],
        "web.assets_backend": [
            "hr_contract_salary_payroll/static/src/js/tours/*.js",
            "hr_contract_salary_payroll/static/src/views/*.js",
        ],
        "web.assets_tests": [
            "hr_contract_salary_payroll/static/tests/tours/*.js",
        ],
    },
    "auto_install": True,
}
