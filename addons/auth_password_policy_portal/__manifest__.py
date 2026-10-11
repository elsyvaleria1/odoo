{
    "name": "Portal Password Policy",
    "category": "Hidden/Tools",
    "summary": "Expose password-policy settings on portal account pages",
    "description": "Pass the configured password-policy requirements to the portal layout. Loads the portal-side assets used for password entry guidance.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "auth_password_policy_signup",
        "portal",
    ],
    "data": [
        "views/templates.xml",
    ],
    "auto_install": True,
}
