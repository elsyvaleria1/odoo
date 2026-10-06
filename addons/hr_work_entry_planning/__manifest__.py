{
    "name": "Planning Work Entries",
    "category": "Human Resources/Employees",
    "sequence": 95,
    "summary": "Generate employee work entries from planned shifts",
    "description": "Adds planning as a work-entry source and links entries to planning slots. Slot changes update the corresponding work entries subject to validation restrictions.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_work_entry_enterprise",
        "planning",
    ],
    "data": [
        "views/hr_employee_views.xml",
        "views/hr_contract_template_views.xml",
    ],
    "demo": [
        "demo/hr_work_entry_planning_demo.xml",
    ],
    "auto_install": True,
}
