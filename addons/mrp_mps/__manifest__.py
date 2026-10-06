{
    "name": "Master Production Schedule",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Supply Chain/Manufacturing",
    "sequence": 50,
    "summary": "Plan replenishment from product demand forecasts",
    "description": "Provides period-based forecasts, target stock and replenishment quantities with actual-demand and supply comparisons. Can launch replenishment using configured manufacturing or purchasing routes.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "base_import",
        "mrp",
        "purchase_stock",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "security/ir.access.csv",
        "views/mrp_mps_views.xml",
        "views/mrp_mps_menu_views.xml",
        "views/mrp_bom_views.xml",
        "views/product_product_views.xml",
        "views/product_template_views.xml",
        "views/res_config_settings_views.xml",
        "wizards/wizard_mrp_production_schedule_view_replenishment_views.xml",
        "wizards/wizard_mrp_production_schedule_update_forecast_views.xml",
    ],
    "demo": [
        "demo/mps_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "mrp_mps/static/src/**/*",
        ],
    },
}
