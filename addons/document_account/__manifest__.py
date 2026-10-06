{
    "name": "Accounting Document Integration",
    "version": "1.1",
    "category": "Productivity/Documents",
    "summary": "Create accounting records from documents and file accounting attachments",
    "description": "Adds document actions for creating accounting entries and bank statements, journal folder synchronization, and accounting report export to Documents. Requires journal and folder configuration and the corresponding accounting access rights.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "document",
        "account",
    ],
    "data": [
        "security/security.xml",
        "security/ir.access.csv",
        "data/document_account_tour.xml",
        "data/ir_actions_server_data.xml",
        "views/account_move_views.xml",
        "views/document_account_folder_setting_views.xml",
        "views/document_document_views.xml",
        "views/ir_actions_server_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_report_formula_export_attachment_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "document_account/static/**/*",
        ],
    },
    "auto_install": True,
    "post_init_hook": "_documents_account_post_init",
}
