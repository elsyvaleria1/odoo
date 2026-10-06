{
    "name": "Employee Survey Certification Records",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Human Resources/Employees",
    "summary": "Record passed certification surveys on linked employee resumes",
    "description": "Creates or updates certification resume entries after a certification survey is completed successfully. Requires an employee linked through the respondent user contact; the configured certification validity determines the end date. These are internal survey results, not independent accreditation.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "hr_skills",
        "survey",
    ],
    "data": [
        "data/hr_resume_data.xml",
        "views/hr_resume_line_views.xml",
        "views/survey_survey_views.xml",
    ],
    "demo": [
        "demo/hr_resume_demo.xml",
    ],
    "auto_install": True,
}
