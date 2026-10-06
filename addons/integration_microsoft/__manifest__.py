{
    "name": "Microsoft Integration",
    "version": "19.0.2.1.0",
    "oldest_upgradable_version": "19.0.2.0.0",
    "category": "Hidden/Tools",
    "summary": "Connect Microsoft Graph through one OAuth client per company",
    "description": "Keeps each company's Microsoft Entra OAuth client in the credential vault and calls Microsoft Graph through the integration transport. Users authorize their own Microsoft account through the standard OAuth flow, so a calendar or another Microsoft feature uses that personal connection. Requires a Microsoft Entra app registration whose redirect URIs list this database's callback; a single-tenant registration sets its tenant in the service's authorization and token URLs.",
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
