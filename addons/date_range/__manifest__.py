{
    "name": "Named Date Ranges",
    "version": "19.0.1.2.1",
    "oldest_upgradable_version": "19.0.1.2.1",
    "category": "Hidden",
    "summary": "Define reusable date ranges and select them in backend filters",
    "description": "Adds date-range types, named periods, parent relationships, overlap rules and generation settings. Supplies a generation wizard, scheduled range creation and backend domain-editor integration, plus a mixin for model search fields. Consumers configure the relevant date field and period types; periods are not limited to calendar months or years.",
    "author": "ACSONE SA/NV, Odoo Community Association (OCA), AgroMarin",
    "website": "https://github.com/OCA/server-ux",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "views/date_range_type_views.xml",
        "views/date_range_views.xml",
        "wizards/wizard_date_range_create_views.xml",
        "views/date_range_menu.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "date_range/static/src/js/date_range_service.js",
            "date_range/static/src/js/date_range_provider.js",
            "date_range/static/src/js/domain_selector.esm.js",
        ],
        "web.assets_unit_tests": [
            "date_range/static/tests/**/*",
        ],
    },
}
