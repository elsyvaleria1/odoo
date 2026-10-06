{
    "name": "Social Formatting and Preview Tests",
    "version": "1.0",
    "category": "Hidden",
    "sequence": 9878,
    "summary": "Test social post formatting and HTML preview behavior across provider dependencies",
    "description": "Loads JavaScript unit tests for the social formatter and post preview interface alongside the declared provider modules. The shipped tests exercise text and link formatting and preview rendering; the dependency list does not imply coverage of every provider interaction.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "social_facebook",
        "social_instagram",
        "social_linkedin",
        "social_push_notifications",
        "social_twitter",
        "social_youtube",
        "social_crm",
    ],
    "assets": {
        "web.assets_unit_tests": [
            "social_test_full/static/tests/**/*",
        ],
    },
}
