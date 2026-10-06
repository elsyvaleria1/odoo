{
    "name": "Automation Webhooks",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Hidden",
    "summary": "Trigger automation rules through configured HTTP webhooks",
    "description": "Adds webhook endpoints, request payload access and rule dispatch. Rules can configure inbound credentials, request logging and rate limits; the selected authentication mode controls access.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "integration",
        "automation",
    ],
    "data": [
        "views/automation_rule_views.xml",
    ],
    "auto_install": True,
}
