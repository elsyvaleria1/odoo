{
    "name": "Website Job Posting Preparation",
    "version": "1.0",
    "category": "Human Resources/Recruitment/Integration",
    "summary": "Prepare website job descriptions and application links for job-board posting",
    "description": "Adds website application URLs and HTML descriptions to job-board posting forms. An optional generation action sends flattened website job text to the configured OLG service and uses its returned content; service access and request limits apply, and generated copy requires review.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_recruitment_integration_base",
        "website_hr_recruitment",
    ],
    "data": [
        "views/hr_job_post_views.xml",
        "wizards/wizard_hr_job_create_post_views.xml",
    ],
    "auto_install": True,
}
