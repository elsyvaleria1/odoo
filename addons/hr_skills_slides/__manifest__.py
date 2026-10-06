{
    "name": "Employee Course Completion Records",
    "version": "1.0",
    "category": "Human Resources/Employees",
    "summary": "Record completed online courses on linked employee resumes",
    "description": "Adds course links and completion displays to employee resumes. The course completion hook creates missing training entries for employees linked through the learner user contact; course enrollment and delivery are supplied by eLearning.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "hr_skills",
        "website_slides",
    ],
    "data": [
        "views/hr_employee_views.xml",
        "views/hr_resume_line_views.xml",
        "views/slide_channel_views.xml",
        "views/hr_skills_slides_menus.xml",
    ],
    "demo": [
        "demo/hr_resume_line_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_skills_slides/static/src/scss/**/*",
            "hr_skills_slides/static/src/fields/**/*",
        ],
    },
    "auto_install": True,
}
