{
    "name": "Module Uninstallation Fixtures",
    "version": "0.1",
    "category": "Hidden/Tests",
    "summary": "Provide models and access records for module uninstallation tests",
    "description": "Load model fixtures and their access rules for testing module removal. The uninstall operation exercises cleanup of the module-owned registry and database objects.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "base",
    ],
    "data": [
        "security/ir.access.csv",
    ],
}
