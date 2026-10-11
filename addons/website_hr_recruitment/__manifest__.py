{
    "name": "Online Jobs",
    "version": "1.1",
    "oldest_upgradable_version": "17.0.1.1",
    "category": "Website/Website",
    "sequence": 310,
    "summary": "Publish job openings and accept website applications",
    "description": "Adds public job listing, detail and application pages linked to recruitment records. Stores website descriptions and publication information on jobs and processes submitted application data. Recruiting teams manage applicants through the recruitment dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_recruitment",
        "website_mail",
    ],
    "data": [
        "security/website_hr_recruitment_security.xml",
        "security/ir.access.csv",
        "data/config_data.xml",
        "views/website_hr_recruitment_templates.xml",
        "views/hr_recruitment_views.xml",
        "views/hr_job_views.xml",
        "views/website_pages_views.xml",
        "views/website_hr_recruitment_menus.xml",
    ],
    "demo": [
        "demo/hr_job_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_hr_recruitment/static/src/scss/**/*",
            "website_hr_recruitment/static/src/interactions/*",
        ],
        "web.assets_backend": [
            "website_hr_recruitment/static/src/js/widgets/copy_link_menuitem.js",
            "website_hr_recruitment/static/src/js/widgets/copy_link_menuitem.xml",
            "website_hr_recruitment/static/src/fields/**/*",
        ],
        "website.website_builder_assets": [
            "website_hr_recruitment/static/src/js/website_hr_recruitment_editor.js",
            "website_hr_recruitment/static/src/website_builder/**/*",
        ],
        "website.assets_editor": [
            "website_hr_recruitment/static/src/js/systray_items/new_content.js",
        ],
        "web.assets_tests": [
            "website_hr_recruitment/static/tests/**/*",
        ],
    },
    "application": True,
    "auto_install": [
        "hr_recruitment",
        "website_mail",
    ],
}
