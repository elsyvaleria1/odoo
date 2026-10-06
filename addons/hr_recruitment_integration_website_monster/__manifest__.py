{
    "name": "Monster Website Application Links",
    "version": "1.0",
    "category": "Human Resources/Recruitment/Integration",
    "summary": "Include website contact and application URLs in Monster job postings",
    "description": "Adds the site base URL to the Monster contact payload. When the posting uses the redirect application method, it also supplies the job website URL as CustomApplyOnlineURL; posting and website recruitment behavior come from the dependencies.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_recruitment_integration_website",
        "hr_recruitment_integration_monster",
    ],
    "auto_install": True,
}
