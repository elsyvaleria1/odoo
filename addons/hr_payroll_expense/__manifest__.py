{
    "name": "Expense Reimbursement in Payslips",
    "version": "1.0",
    "category": "Human Resources/Payroll",
    "sequence": 95,
    "summary": "Include eligible employee-paid expenses in payslip reimbursement",
    "description": "Links approved or posted employee-paid expenses marked for payroll reimbursement to draft payslips and updates their expense inputs. Requires a payroll structure with an expense rule; posting and reconciliation connect the expense accounting entries to the payslip.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_expense",
        "hr_payroll_account",
    ],
    "data": [
        "views/hr_expense_views.xml",
        "views/hr_payslip_views.xml",
        "data/hr_payroll_expense_data.xml",
        "wizards/wizard_account_move_line_pay_views.xml",
    ],
    "demo": [
        "demo/hr_payroll_expense_demo.xml",
    ],
    "auto_install": True,
}
