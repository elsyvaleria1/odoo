{
    "name": "Appraisal Skill Assessments",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Human Resources/Appraisals",
    "sequence": 280,
    "summary": "Assess employee skills during appraisals and compare target job requirements",
    "description": "Copies employee skills into confirmed appraisals and applies assessed skill changes through the appraisal workflow. Adds target-job skill comparisons, skill reporting and skill-related goals; requires employee skill records and the appraisal process.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "hr_appraisal",
        "hr_skills",
    ],
    "data": [
        "security/ir.access.csv",
        "views/hr_skills_views.xml",
        "views/hr_appraisal_goal_template_views.xml",
        "views/hr_appraisal_goal_template_skill_views.xml",
        "views/hr_appraisal_skill_views.xml",
        "views/hr_appraisal_skills_templates.xml",
        "views/hr_appraisal_goal_views.xml",
        "reports/hr_appraisal_skill_report_views.xml",
        "views/hr_appraisal_skills_menus.xml",
    ],
    "demo": [
        "demo/hr_appraisal_skills_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_appraisal_skills/static/src/**/*",
        ],
    },
    "auto_install": True,
    "post_init_hook": "_update_skills_for_confirmed",
}
