{
    "name": "Recruitment Analysis",
    "version": "1.0",
    "category": "Human Resources/Recruitment",
    "summary": "Analyse applicants and recruitment stage progression",
    "description": "Add recruitment and stage analysis reports with applicant drill-down actions. Includes recruitment leaderboard calculations.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/recruitment",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_recruitment",
    ],
    "data": [
        "security/ir.access.csv",
        "reports/hr_recruitment_report_views.xml",
        "reports/hr_recruitment_stage_report_views.xml",
        "views/hr_recruitment_reports_menus.xml",
    ],
    "demo": [
        "demo/hr_recruitment_reports_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_recruitment_reports/static/src/components/**",
            "hr_recruitment_reports/static/src/js/**",
        ],
    },
    "auto_install": True,
}
