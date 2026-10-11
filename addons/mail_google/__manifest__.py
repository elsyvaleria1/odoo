{
    "name": "Gmail Mail Server Authentication",
    "version": "19.0.2.2.0",
    "oldest_upgradable_version": "19.0.2.1.0",
    "category": "Hidden",
    "summary": "Authorize incoming and outgoing mail servers with Gmail OAuth",
    "description": "Authorizes Gmail outgoing and incoming mail servers through the company's Google OAuth client: each server holds its own connection to Google, a personal server authorized by the account it sends as, and logs in with XOAUTH2. Requires the Google OAuth client set under Settings, Integrations.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "mail_oauth2",
        "integration_google",
    ],
    "data": [
        "views/fetchmail_server_views.xml",
        "views/ir_mail_server_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "auto_install": True,
}
