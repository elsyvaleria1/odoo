{
    "name": "LDAP Authentication",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Hidden/Tools",
    "summary": "Authenticate users against configured LDAP directories",
    "description": "Connect to an LDAP server to check user credentials and map directory attributes. Company LDAP configuration controls the directory search and user-creation behaviour.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "credential",
        "web",
    ],
    "external_dependencies": {
        "python": [
            "python-ldap",
        ],
        "apt": {
            "python-ldap": "python3-ldap",
        },
    },
    "data": [
        "views/ldap_installer_views.xml",
        "security/ir.access.csv",
        "views/res_config_settings_views.xml",
    ],
}
