{
    "name": "Employee Timeline Resources",
    "version": "1.0",
    "category": "Human Resources/Employees",
    "summary": "Use employee resources in Gantt views",
    "description": "Adds employee-specific support and frontend components for timeline views supplied by dependent applications.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "hr",
        "web_gantt",
    ],
    "assets": {
        "web.assets_backend": [
            "hr_gantt/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "hr_gantt/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
