{
    "name": "Sales Commission Payslip Inputs",
    "version": "1.0",
    "category": "Human Resources/Payroll",
    "sequence": 95,
    "summary": "Populate payslip inputs from configured sales commission plans",
    "description": "Adds a payslip input type to commission plans and aggregates matching commission report entries for each employee user, company and payslip payment-date range. Amounts are converted to the payslip currency; salary rules and payroll payment processing are supplied by Payroll.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sale_commission",
        "hr_payroll",
    ],
    "data": [
        "views/sale_commission_plan.xml",
    ],
    "auto_install": True,
}
