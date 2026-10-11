{
    "name": "Employee Signature Requests",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Human Resources",
    "summary": "Send and track documents for employee signatures",
    "description": "Adds employee and contract signature links, request wizards and signature activities in employee plans.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr",
        "sign",
    ],
    "data": [
        "security/security.xml",
        "security/ir.access.csv",
        "wizards/wizard_hr_employee_send_sign_request_views.xml",
        "views/hr_employee_view.xml",
        "views/sign_request_views.xml",
        "views/mail_activity_plan_views.xml",
        "views/mail_activity_plan_template_views.xml",
        "data/hr_sign_data.xml",
    ],
    "demo": [
        "demo/hr_sign_demo.xml",
    ],
    "auto_install": True,
}
