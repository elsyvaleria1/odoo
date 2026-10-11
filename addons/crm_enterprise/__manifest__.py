{
    "name": "CRM Maps and Cohorts",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Sales/CRM",
    "summary": "Review leads on maps and in cohort analyses",
    "description": "Adds lead map and cohort views and their frontend behavior. Map placement depends on the geographic information available on contacts.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "crm",
        "web_cohort",
        "web_map",
    ],
    "data": [
        "views/crm_lead_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "crm_enterprise/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "crm_enterprise/static/tests/**/*",
        ],
    },
    "auto_install": [
        "crm",
    ],
}
