{
    "name": "Payroll ISO 20022 Payment Files",
    "version": "1.0",
    "category": "Human Resources/Payroll",
    "summary": "Export payroll payments in the supported ISO 20022 format",
    "description": "Adds a bank-journal selection and SEPA payment-file export to payroll payment reports, with employee IBAN validation. Bank acceptance depends on the configured payment format and account data.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_payroll_account",
        "account_iso20022",
    ],
    "data": [
        "views/hr_payslip_views.xml",
        "views/hr_payslip_run_views.xml",
        "data/hr_payroll_dashboard_warning_data.xml",
        "wizards/wizard_hr_payslip_export_payment_file_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_payroll_account_iso20022/static/src/**/*.js",
            "hr_payroll_account_iso20022/static/src/**/*.scss",
            "hr_payroll_account_iso20022/static/src/**/*.xml",
        ],
    },
}
