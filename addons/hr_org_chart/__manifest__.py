{
    "name": "Employee Organization Chart",
    "version": "1.0",
    "category": "Human Resources",
    "summary": "Browse employee managers and subordinates in an organization chart",
    "description": "Add organization-chart views and data endpoints for employees. Resolve managers, subordinate relationships and links to employee records.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr",
        "web_hierarchy",
    ],
    "data": [
        "views/hr_department_views.xml",
        "views/hr_views.xml",
    ],
    "assets": {
        "web._assets_primary_variables": [
            "hr_org_chart/static/src/scss/variables.scss",
        ],
        "web.assets_backend": [
            "hr_org_chart/static/src/fields/*",
            "hr_org_chart/static/src/views/**/*",
        ],
        "web.assets_tests": [
            "hr_org_chart/static/tests/tours/*.js",
        ],
        "web.assets_unit_tests": [
            "hr_org_chart/static/tests/**/*",
        ],
    },
    "auto_install": [
        "hr",
    ],
}
