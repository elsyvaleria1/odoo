{
    "name": "Recruitment Interview Surveys",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Human Resources",
    "summary": "Send job interview surveys to applicants and link their responses",
    "description": "Adds interview survey selection on jobs, applicant invitation and response actions, and recruitment-specific survey views. Requires a configured survey; question content and scoring are defined through the Survey dependency.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "survey",
        "hr_recruitment",
    ],
    "data": [
        "security/ir.access.csv",
        "data/mail_template_data.xml",
        "views/hr_job_views.xml",
        "views/hr_applicant_views.xml",
        "views/res_config_setting_views.xml",
        "views/survey_survey_views.xml",
        "views/survey_templates_statistics.xml",
        "views/hr_recruitment_survey_menus.xml",
    ],
    "demo": [
        "demo/survey_demo.xml",
        "demo/hr_job_demo.xml",
    ],
}
