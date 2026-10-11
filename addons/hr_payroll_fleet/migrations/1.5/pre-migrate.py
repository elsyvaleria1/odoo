def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE ir_model_data SET noupdate = FALSE
         WHERE module = 'hr_payroll_fleet'
           AND name = 'hr_payroll_dashboard_warning_employee_multiple_cars'
        """
    )
