{
    "name": "Microsoft Account Connection",
    "version": "19.0.2.0.0",
    "oldest_upgradable_version": "19.0.2.0.0",
    "category": "Hidden/Tools",
    "summary": "Authorize Microsoft service access and refresh OAuth tokens",
    "description": "Provide authorization and token storage for Microsoft service integrations. Dependent modules use the configured client and requested service scopes.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "web",
        "credential",
    ],
    "data": [
        "data/microsoft_account_data.xml",
    ],
}
