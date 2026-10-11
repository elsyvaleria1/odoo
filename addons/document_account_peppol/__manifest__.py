{
    "name": "Peppol Document Reception",
    "version": "1.0",
    "category": "Productivity/Documents",
    "summary": "File received Peppol attachments in the configured Documents folder",
    "description": "Overrides Peppol invoice import when the company reception mode is Documents. Creates a document from the received attachment with configured folder and tags; other reception modes retain the accounting import path. Peppol connectivity comes from the dependency.",
    "author": "Odoo SA",
    "license": "Other OSI approved licence",
    "depends": [
        "account_peppol",
        "document",
    ],
    "data": [
        "views/res_config_settings_views.xml",
    ],
    "auto_install": True,
}
