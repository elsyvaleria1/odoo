{
    "name": "Data Module Import",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden/Tools",
    "summary": "Import custom data modules from uploaded archives",
    "description": "Allow authorized users to upload modules containing declarative data and static assets. Handles their manifest metadata, dependencies and module data loading.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/wizard_ir_module_module_import_views.xml",
        "views/ir_module_views.xml",
        "views/base_import_module_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "base_import_module/static/src/**/*",
        ],
    },
    "auto_install": True,
}
