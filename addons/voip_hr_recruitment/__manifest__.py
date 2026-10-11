{
    "name": "Call Applicant Links",
    "version": "1.0",
    "category": "Human Resources/Recruitment",
    "summary": "Open related job applications from phone calls",
    "description": "Adds application counts and navigation to call records, with applicant access checks and caller data.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr_recruitment",
        "voip",
    ],
    "data": [
        "views/phone_call_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "voip_hr_recruitment/static/src/**/*",
        ],
    },
    "auto_install": True,
}
