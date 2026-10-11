{
    "name": "Company Contact Enrichment",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Hidden/Tools",
    "summary": "Look up company details when creating contacts",
    "description": "Requests company suggestions and enrichment data by supported identifiers from the IAP service. Results depend on service coverage and access or credits.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "iap_mail",
    ],
    "external_dependencies": {
        "python": [
            "python-stdnum",
        ],
        "apt": {
            "python-stdnum": "python3-stdnum",
        },
    },
    "data": [
        "security/ir.access.csv",
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
        "data/iap_service_data.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "partner_autocomplete/static/src/scss/*",
            "partner_autocomplete/static/src/js/*",
            "partner_autocomplete/static/src/xml/*",
        ],
        "web.assets_unit_tests": [
            "partner_autocomplete/static/tests/**/*",
        ],
    },
    "esm": {
        "external_libs": {
            "jsvat": "/partner_autocomplete/static/lib/jsvat.js",
        },
    },
}
