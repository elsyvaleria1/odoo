{
    "name": "Expense Accounting Review",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Add employee-expense checks to accounting return reviews",
    "description": "Load the expense-related accounting return check template. The check is used by the accounting review workflow with employee expenses installed.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/accounting",
    "license": "OEEL-1",
    "depends": [
        "accountant",
        "hr_expense",
    ],
    "data": [
        "views/account_return_check_template.xml",
    ],
    "auto_install": True,
}
