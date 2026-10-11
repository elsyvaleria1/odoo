{
    "name": "Document Signature Integration",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Productivity/Documents",
    "summary": "Create signing templates from documents and file completed signed documents",
    "description": "Adds document actions and import dialogs for signature templates, completed-document filing and signer access. Requires the Sign workflow and configured document folders; it does not itself provide external signer identity verification.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "document",
        "sign",
    ],
    "data": [
        "security/ir.access.csv",
        "data/document_folder_data.xml",
        "data/ir_action_server_data.xml",
        "views/sign_templates.xml",
        "views/res_config_settings.xml",
        "wizards/wizard_sign_template_import_document_views.xml",
        "wizards/wizard_sign_request_send_views.xml",
    ],
    "demo": [
        "demo/document_document_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "document_sign/static/src/backend_components/**/*",
        ],
    },
    "auto_install": True,
}
