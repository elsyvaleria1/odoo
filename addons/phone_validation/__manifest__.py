{
    "name": "Phone Number Formatting and Blacklists",
    "version": "2.2",
    "oldest_upgradable_version": "2.2",
    "category": "Hidden",
    "sequence": 9999,
    "summary": "Normalize phone numbers and manage phone blacklist records",
    "description": "Adds country-aware parsing and formatting through phonenumbers, normalized number lookup and blacklist management. Provides phone-aware model helpers and a mail-thread mixin for adopting records; format validation does not establish ownership or reachability of a number, and delivery integrations must apply blacklist rules.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "base",
        "mail",
    ],
    "external_dependencies": {
        "python": [
            "phonenumbers",
        ],
        "apt": {
            "phonenumbers": "python3-phonenumbers",
        },
    },
    "data": [
        "security/ir.access.csv",
        "views/phone_blacklist_views.xml",
        "views/res_partner_views.xml",
        "wizards/wizard_phone_blacklist_archive_views.xml",
        "views/phone_validation_menus.xml",
    ],
    "auto_install": True,
}
