def migrate(cr, version):
    if not version:
        return
    # the warning's query reads the vehicle's company and activity from its
    # resource now; a noupdate record takes the new query only when let
    cr.execute(
        """
        UPDATE ir_model_data SET noupdate = FALSE
         WHERE module = 'hr_payroll_fleet'
           AND name = 'hr_payroll_dashboard_warning_employee_multiple_cars'
        """
    )
