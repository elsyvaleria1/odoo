{
    "name": "Recruitment AI Refusal Assistance",
    "version": "1.0",
    "category": "Human Resources/Recruitment",
    "summary": "Add AI assistance to applicant refusal messages",
    "description": "Extend the applicant refusal wizard view with AI message assistance. Uses the AI and recruitment features declared by the module.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_recruitment",
        "ai",
    ],
    "data": [
        "wizards/wizard_hr_applicant_refuse_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_recruitment_ai/static/src/mail_composer_chatgpt.js",
        ],
    },
    "auto_install": [
        "hr_recruitment",
        "ai",
    ],
}
