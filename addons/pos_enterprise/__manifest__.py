{
    "name": "POS Preparation Displays",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Sales/Point of Sale",
    "summary": "Track order preparation stages and preparation times",
    "description": "Provides preparation displays, order-stage management and preparation-time reports with POS integration. Displays and stages must be configured for the relevant POS.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "point_of_sale",
    ],
    "data": [
        "security/ir.access.csv",
        "views/res_config_settings_views.xml",
        "views/preparation_display_assets_index.xml",
        "views/preparation_display_view.xml",
        "wizards/wizard_pos_prep_display_reset_views.xml",
        "data/preparation_display_cron.xml",
        "views/pos_order_view.xml",
        "views/pos_preparation_time_report_view.xml",
        "views/pos_enterprise_menus.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "pos_enterprise/static/src/override/point_of_sale/**/*",
            (
                "remove",
                "pos_enterprise/static/src/override/point_of_sale/**/*.dark.scss",
            ),
        ],
        "point_of_sale.assets_prod_dark": [
            "pos_enterprise/static/src/**/*.dark.scss",
        ],
        "pos_preparation_display.assets": [
            "web/static/src/scss/functions.scss",
            "pos_enterprise/static/src/scss/primary_variables.scss",
            (
                "include",
                "point_of_sale.base_app",
            ),
            "web/static/src/webclient/webclient.scss",
            "web/static/src/webclient/icons.scss",
            "point_of_sale/static/src/utils.js",
            "point_of_sale/static/src/app/utils/devices_identifier_sequence.js",
            "mail/static/src/core/common/sound_effects_service.js",
            "point_of_sale/static/src/overrides/sound_effects_service.js",
            "pos_enterprise/static/src/app/**/*",
            "point_of_sale/static/src/proxy_trap.js",
            "point_of_sale/static/src/lazy_getter.js",
            "point_of_sale/static/src/app/models/data_service_options.js",
            "point_of_sale/static/src/app/models/utils/indexed_db.js",
            "point_of_sale/static/src/app/utils/pretty_console_log.js",
            "point_of_sale/static/src/app/models/related_models/**/*",
            "point_of_sale/static/src/app/utils/offline_queue.js",
            "point_of_sale/static/src/app/utils/optimistic_updates.js",
            "point_of_sale/static/src/app/services/data_service.js",
            "point_of_sale/static/src/app/models/pos_preset.js",
            "point_of_sale/static/src/app/models/pos_category.js",
        ],
        "pos_preparation_display.assets_tour_tests": [
            (
                "include",
                "point_of_sale.base_tests",
            ),
            "pos_enterprise/static/tests/tours/preparation_display/**/*",
        ],
        "web.assets_tests": [
            "pos_enterprise/static/tests/tours/point_of_sale/**/*",
        ],
        "web.assets_backend": [
            "pos_enterprise/static/src/clickbot_entries.js",
            "pos_enterprise/static/src/backend/components/fields/duration_field.js",
            "pos_enterprise/static/src/backend/components/fields/duration_field.xml",
        ],
        "web.assets_unit_tests_setup": [
            (
                "include",
                "pos_preparation_display.assets",
            ),
            (
                "remove",
                "pos_enterprise/static/src/app/root.js",
            ),
            (
                "remove",
                "pos_enterprise/static/src/**/*.scss",
            ),
            "web/static/src/webclient/debug/**/*",
            "web/static/src/core/browser/router.js",
        ],
        "web.assets_unit_tests": [
            "pos_enterprise/static/tests/unit/**/*",
        ],
    },
    "esm": {
        "bundles": [
            "pos_preparation_display.assets",
            "pos_preparation_display.assets_tour_tests",
        ],
        "secondary_import_map_includes": {
            "pos_preparation_display.assets": [
                "pos_preparation_display.assets_tour_tests",
            ],
        },
    },
    "auto_install": True,
}
