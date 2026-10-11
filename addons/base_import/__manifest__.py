{
    "name": "Record Import",
    "version": "2.2",
    "oldest_upgradable_version": "2.2",
    "category": "Hidden/Tools",
    "summary": "Import business records from tabular files",
    "description": "Provide file parsing, field mapping, validation and record-loading tools. Supported spreadsheet formats depend on the available parsing libraries.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "external_dependencies": {
        "python": [
            "chardet",
        ],
        "apt": {
            "chardet": "python3-chardet",
        },
    },
    "data": [
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "base_import/static/src/**/*.scss",
            "base_import/static/src/**/*.js",
            "base_import/static/src/**/*.xml",
        ],
        "web.assets_unit_tests": [
            "base_import/static/tests/**/*.test.js",
        ],
    },
    "auto_install": True,
}
