{
    "name": "Invoice EDI Proxy Connection",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Accounting/Accounting",
    "summary": "Register and authenticate database connections to invoice EDI proxies",
    "description": "Manage proxy registrations, request authentication and tokens for invoice EDI services. Dependent integrations supply the proxy type and service-specific document flow.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "account",
        "certificate",
        "integration",
    ],
    "data": [
        "security/ir.access.csv",
        "views/account_edi_proxy_user_views.xml",
        "views/account_edi_proxy_client_menus.xml",
    ],
    "post_init_hook": "_create_demo_config_param",
}
