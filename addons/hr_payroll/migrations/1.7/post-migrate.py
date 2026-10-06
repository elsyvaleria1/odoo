from odoo.tools import SQL

CODE_COLUMNS = {
    "hr_salary_rule": (
        "condition_python",
        "amount_python_compute",
        "amount_percentage_base",
        "quantity",
    ),
    "hr_payroll_dashboard_warning": ("evaluation_code",),
}


def migrate(cr, version):
    if not version:
        return
    # hr.employee.country_id is nationality_country_id (hr 1.33); a rule a user
    # wrote still names the old field and would fail when the payslip computes
    for table, columns in CODE_COLUMNS.items():
        for column in columns:
            cr.execute(
                SQL(
                    r"UPDATE %(table)s SET %(column)s = regexp_replace("
                    r"%(column)s, '\memployee\.country_id\M',"
                    r" 'employee.nationality_country_id', 'g')"
                    r" WHERE %(column)s ~ '\memployee\.country_id\M'",
                    table=SQL.identifier(table),
                    column=SQL.identifier(column),
                )
            )
