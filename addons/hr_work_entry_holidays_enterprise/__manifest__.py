{
    "name": "Work Entry Time Off Controls",
    "version": "1.0",
    "category": "Human Resources/Payroll",
    "sequence": 95,
    "summary": "Expose leave approval and refusal controls on conflicting work entries",
    "description": "Extends work entry forms with linked leave information and buttons to approve or refuse the leave behind a conflict. Adds leave-type display on work entry types; leave workflow methods belong to the dependency.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_work_entry_holidays",
    ],
    "data": [
        "views/hr_work_entry_views.xml",
    ],
    "auto_install": True,
}
