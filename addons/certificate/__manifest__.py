{
    "name": "Certificates and Cryptographic Keys",
    "version": "19.0.1.2.0",
    "oldest_upgradable_version": "19.0.1.2.0",
    "category": "Hidden/Tools",
    "summary": "Store certificates and keys for signing and verification",
    "description": "Parses certificate metadata and validity dates, associates private keys and exposes signing and signature-verification helpers. Supports encrypted credential storage through its dependencies; callers select the supported algorithm and supply compatible keys.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "credential",
        "web",
        "mixin_encryption",
    ],
    "data": [
        "security/ir.access.csv",
        "views/certificate_views.xml",
        "views/key_views.xml",
        "views/action_menus.xml",
        "views/res_config_settings_view.xml",
    ],
}
