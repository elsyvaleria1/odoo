{
    "name": "Approvals - Employee Managers",
    "version": "19.0.1.1.5",
    "oldest_upgradable_version": "19.0.1.1.4",
    "category": "Human Resources/Approvals",
    "sequence": 192,
    "summary": "Resolve approval managers and escalation chains from employee reporting lines",
    "description": "Extends approval categories and requests with requester-manager steps, employee manager chains and department access settings. Resolution uses an employee in the request company and a suitable active manager user. Required-manager and minimum-approver checks run when submitting a request; employee and user relationships must be configured.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "approval_app",
        "hr",
    ],
    "data": [
        "security/ir.access.csv",
        "data/approval_category_data.xml",
        "views/hr_department_views.xml",
        "views/approval_category_views.xml",
    ],
    "demo": [
        "demo/approval_hr_demo.xml",
    ],
    "auto_install": True,
}
