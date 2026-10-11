{
    "name": "Phone SMS Actions",
    "version": "1.0",
    "category": "Sales/Sales",
    "summary": "Open SMS messaging from the phone interface",
    "description": "Load phone-client extensions for SMS actions. Message delivery uses the configured SMS service.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "voip",
        "sms",
    ],
    "assets": {
        "web.assets_backend": [
            "voip_sms/static/src/**/*",
        ],
    },
    "auto_install": True,
}
