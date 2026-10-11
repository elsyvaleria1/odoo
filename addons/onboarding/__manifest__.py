{
    "name": "Onboarding Steps",
    "version": "1.2",
    "category": "Hidden",
    "sequence": 9001,
    "summary": "Track onboarding steps and completion for application setup",
    "description": "Define onboarding panels and their steps. Store completion progress so applications can guide users through their configuration actions.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "data": [
        "views/onboarding_templates.xml",
        "views/onboarding_views.xml",
        "views/onboarding_menus.xml",
        "security/ir.access.csv",
    ],
    "assets": {
        "web.assets_backend": [
            "onboarding/static/src/**/*",
        ],
        "web._assets_primary_variables": [
            "onboarding/static/src/scss/onboarding.variables.scss",
        ],
    },
}
