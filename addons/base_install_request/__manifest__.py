{
    "name": "Module Installation Requests",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Hidden",
    "summary": "Let internal users request application installation",
    "description": "Collect installation requests and send them to users responsible for application management. Provides request views and actions for reviewing and installing requested modules.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mail",
    ],
    "data": [
        "security/ir.access.csv",
        "wizards/base_module_install_request_views.xml",
        "data/mail_template_data.xml",
        "data/mail_templates_module_install.xml",
        "views/ir_module_module_views.xml",
    ],
    "auto_install": True,
    "post_init_hook": "_auto_install_apps",
}
