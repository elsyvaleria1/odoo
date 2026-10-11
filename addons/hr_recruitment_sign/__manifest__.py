{
    "name": "Applicant Signature Requests",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Human Resources/Recruitment",
    "summary": "Send signature requests to job applicants",
    "description": "Adds applicant signature counts and a wizard to choose templates, signers and message content. Links applicable signature records when an applicant becomes an employee.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_recruitment",
        "hr_sign",
    ],
    "data": [
        "security/ir.access.csv",
        "data/mail_templates_chatter.xml",
        "wizards/wizard_hr_applicant_send_sign_request_views.xml",
        "views/hr_applicant_views.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "hr_recruitment_sign/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
