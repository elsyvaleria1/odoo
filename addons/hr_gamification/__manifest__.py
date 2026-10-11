{
    "name": "Employee Badges and Goals",
    "version": "1.1",
    "category": "Human Resources",
    "summary": "Grant badges to employees and show their challenge progress",
    "description": "Connect gamification badges and goals to employee records. Adds employee badge views and a grant wizard for authorized users.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "gamification",
        "hr",
    ],
    "data": [
        "security/ir.access.csv",
        "security/ir_access.xml",
        "wizards/wizard_gamification_badge_grant_views.xml",
        "views/gamification_views.xml",
        "views/hr_employee_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_gamification/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "hr_gamification/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
