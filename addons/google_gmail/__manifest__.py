{
    "name": "Gmail Mail Server Authentication",
    "version": "19.0.2.1.0",
    "oldest_upgradable_version": "19.0.2.1.0",
    "category": "Hidden",
    "summary": "Authorize incoming and outgoing mail servers with Gmail OAuth",
    "description": "Add Gmail authorization callbacks and token handling to mail server configuration. Requires a configured Google client or the supported account-connection service.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "mail_oauth2",
        "mail",
    ],
    "data": [
        "views/fetchmail_server_views.xml",
        "views/ir_mail_server_views.xml",
        "views/res_config_settings_views.xml",
        "views/templates.xml",
    ],
    "auto_install": True,
}
