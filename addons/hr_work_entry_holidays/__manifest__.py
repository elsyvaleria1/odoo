{
    "name": "Time Off Work Entries",
    "version": "1.0",
    "category": "Human Resources/Payroll",
    "sequence": 95,
    "summary": "Generate and reconcile work entries for employee time off",
    "description": "Map approved leave intervals to work-entry types. Update work entries and handle leave conflicts when time-off requests are validated, refused or cancelled.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "hr_holidays",
        "hr_work_entry",
    ],
    "data": [
        "data/hr_leave_type_data.xml",
        "views/hr_leave_type_form_views.xml",
        "views/hr_leave_type_views.xml",
    ],
    "demo": [
        "demo/hr_payroll_holidays_demo.xml",
    ],
    "auto_install": True,
    "post_init_hook": "_check_existing_work_entries",
}
