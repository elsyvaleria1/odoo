{
    "name": "Model RPC Endpoints",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden/Tools",
    "summary": "Expose model RPC calls and their contract documentation",
    "description": "Provide model-call endpoints and documentation for accessible models and methods. Authentication and the caller's model access determine which calls are permitted.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "base",
    ],
    "data": [
        "security/res_groups.xml",
    ],
    "auto_install": True,
}
