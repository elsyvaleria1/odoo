{
    "name": "Applicant SMS Composer",
    "version": "1.0",
    "category": "Human Resources/Recruitment",
    "summary": "Compose text messages for applicants",
    "description": "Adds an SMS action to applicant records using the shared message composer and configured SMS service.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "hr_recruitment",
        "sms",
    ],
    "data": [
        "views/hr_applicant_views.xml",
    ],
    "auto_install": True,
}
