{
    "name": "Monster Job Posting",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Human Resources/Recruitment/Integration",
    "summary": "Submit job postings and removal requests through the Monster SOAP integration",
    "description": "Adds Monster posting payloads, platform configuration and job-removal requests through the Monster Business Gateway. Requires company Monster credentials, service access and the zeep library; publication depends on the external service accepting the request.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "credential",
        "hr_recruitment_integration_base",
    ],
    "external_dependencies": {
        "python": [
            "zeep",
        ],
        "apt": {
            "zeep": "python3-zeep",
        },
    },
    "data": [
        "data/hr_recruitment_platform_data.xml",
        "data/res_currency_data.xml",
        "data/hr_contract_type_data.xml",
        "data/res_partner_industry_data.xml",
        "views/res_currency_views.xml",
        "views/res_partner_industry_views.xml",
        "views/hr_contract_type_views.xml",
        "views/res_config_settings.xml",
    ],
}
