{
    "name": "Automatic Currency Rates",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Import exchange rates from configured rate providers",
    "description": "Fetch provider exchange-rate data and create company currency rates. Settings choose the provider and scheduled update frequency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "account",
    ],
    "external_dependencies": {
        "python": [
            "zeep",
        ],
        "apt": {
            "zeep": "python3-zeep",
        },
    },
    "data": [
        "views/res_config_settings_views.xml",
        "views/service_cron_data.xml",
    ],
    "auto_install": True,
}
