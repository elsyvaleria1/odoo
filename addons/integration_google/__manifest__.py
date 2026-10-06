{
    "name": "Google Integration",
    "version": "19.0.2.0.0",
    "category": "Hidden/Tools",
    "summary": "Connect Google APIs through one OAuth client per company",
    "description": "Keeps each company's Google OAuth client in the credential vault and calls Google APIs through the integration transport. Users authorize their own Google account through the standard OAuth flow, so a calendar or another Google feature uses that personal connection; an authorization keeps the scopes granted before it. Requires a Google Cloud OAuth client whose authorized redirect URIs list this database's callback.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "integration",
    ],
    "data": [
        "data/integration_service_data.xml",
        "views/res_config_settings_views.xml",
    ],
}
