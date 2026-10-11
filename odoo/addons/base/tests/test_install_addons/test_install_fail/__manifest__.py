{
    "name": "Addon Installation Fail Fixture",
    "version": "1.0",
    "category": "Hidden/Tools",
    "summary": "Exercise failed addon installation with an invalid currency view fixture",
    "description": "Load the currency view fixture used to provoke an installation failure. Depends on the installation base fixture for the rollback test scenario.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "test_install_base",
    ],
    "data": [
        "views/res_currency_views.xml",
    ],
}
