{
    "name": "Employee Work Locations",
    "version": "2.3",
    "oldest_upgradable_version": "2.3",
    "category": "Human Resources/Remote Work",
    "summary": "Plan weekly employee work locations and date-specific exceptions",
    "description": "Maintain an employee's usual work location by weekday and temporary location changes. Compute the current location and its presence display.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr",
    ],
    "data": [
        "security/ir.access.csv",
        "views/hr_employee_views.xml",
        "views/res_users.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_homeworking/static/src/**/*",
        ],
        "mail.assets_core_common": [
            "hr_homeworking/static/src/work_location_presence.js",
            "hr_homeworking/static/src/components/work_location_presence/**/*",
        ],
        "mail.assets_discuss_core_common": [
            "hr_homeworking/static/src/work_location_presence.js",
            "hr_homeworking/static/src/components/work_location_presence/**/*",
        ],
        "mail.assets_public": [
            "hr_homeworking/static/src/work_location_presence.js",
            "hr_homeworking/static/src/components/work_location_presence/**/*",
        ],
        "im_livechat.assets_embed_core": [
            "hr_homeworking/static/src/work_location_presence.js",
            "hr_homeworking/static/src/components/work_location_presence/**/*",
        ],
        "web.assets_unit_tests": [
            "hr_homeworking/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
