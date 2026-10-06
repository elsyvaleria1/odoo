{
    "name": "Job Board Integration Foundation",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Human Resources/Recruitment/Integration",
    "summary": "Manage external job postings through configurable recruitment platforms",
    "description": "Provide platform, job-post and posting-wizard models with scheduled campaign updates. Platform-specific integrations implement the external service operations.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_recruitment",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "views/hr_job_post_views.xml",
        "views/hr_job_views.xml",
        "views/hr_recruitment_platform_views.xml",
        "wizards/wizard_hr_job_create_post_views.xml",
        "views/hr_recruitment_integration_base_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_recruitment_integration_base/static/src/**/*.js",
            "hr_recruitment_integration_base/static/src/**/*.xml",
            "hr_recruitment_integration_base/static/src/**/*.scss",
        ],
    },
}
