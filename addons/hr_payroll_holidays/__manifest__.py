{
    "name": "Payroll Time Off Adjustments",
    "version": "1.0",
    "category": "Human Resources/Payroll",
    "sequence": 95,
    "summary": "Reconcile employee time off with computed payslips",
    "description": "Check leave requests against payslip periods and handle time-off changes affecting payroll. Adds payroll-related leave activities and payslip error checks.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_holidays_gantt",
        "hr_work_entry_holidays",
        "hr_payroll",
    ],
    "data": [
        "security/hr_payroll_holidays_security.xml",
        "views/res_config_settings_views.xml",
        "views/hr_leave_views.xml",
        "data/mail_activity_data.xml",
        "data/ir_actions_server_data.xml",
        "data/hr_payroll_dashboard_warning_data.xml",
        "views/hr_payroll_holidays_menus.xml",
    ],
    "demo": [
        "demo/demo.xml",
    ],
    "auto_install": True,
}
