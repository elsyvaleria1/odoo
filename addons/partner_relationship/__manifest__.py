{
    "name": "Contact Relationships",
    "version": "19.0.1.0.2",
    "oldest_upgradable_version": "19.0.1.0.2",
    "category": "Sales/CRM",
    "summary": "Record typed relationships and inspect paths between contacts",
    "description": "Adds relationship types and dated links between contacts, including inverse labels and relationship attributes. Provides contact relationship views and a path-inspection wizard. Network results reflect recorded links and configured types rather than independently verified personal or commercial relationships.",
    "author": "AgroMarin",
    "website": "https://agromarin.mx",
    "license": "Other OSI approved licence",
    "depends": [
        "partner",
        "web",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "data/res_partner_relation_type_data.xml",
        "views/res_partner_relation_type_views.xml",
        "views/res_partner_relation_views.xml",
        "views/res_partner_views.xml",
        "wizards/partner_relation_path_views.xml",
        "views/ir_ui_menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "partner_relationship/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "partner_relationship/static/tests/**/*.js",
            (
                "remove",
                "partner_relationship/static/tests/tours/**/*.js",
            ),
        ],
        "web.assets_tests": [
            "partner_relationship/static/tests/tours/**/*.js",
        ],
    },
}
