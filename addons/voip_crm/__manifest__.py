{
    "name": "VoIP CRM Navigation",
    "version": "1.0",
    "category": "Sales/CRM",
    "summary": "Connect call views and contact information to CRM opportunities",
    "description": "Adds CRM actions, opportunity information in phone contact data and CRM-specific call interface extensions. Requires CRM access and a configured VoIP service for calling; call transport is implemented by the VoIP dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "crm",
        "voip",
    ],
    "data": [
        "views/crm_lead_views.xml",
        "views/phone_call_views.xml",
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "voip_crm/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "voip_crm/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
