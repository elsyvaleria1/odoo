{
    "name": "Sales Commissions",
    "version": "1.3",
    "oldest_upgradable_version": "1.3",
    "category": "Sales/Commission",
    "sequence": 105,
    "summary": "Calculate salesperson or team commissions from configured plans",
    "description": "Defines commission plans, achievement rules, targets, forecasts and reporting. Calculations use eligible sales and invoice data and the plan dates and rates.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale",
        "sale_team",
    ],
    "data": [
        "security/security.xml",
        "security/ir.access.csv",
        "views/sale_commission_settings.xml",
        "wizards/wizard_sale_commission_plan_add_user_views.xml",
        "views/sale_commission_plan_view.xml",
        "views/sale_commission_achievement_view.xml",
        "views/sale_commission_forecast_view.xml",
        "views/crm_team_views.xml",
        "reports/commission_report.xml",
        "reports/achievement_report.xml",
        "views/sale_commission_menu.xml",
    ],
    "demo": [
        "demo/sale_commission_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sale_commission/static/src/js/commission_plan_graph/commission_plan_graph.js",
            "sale_commission/static/src/js/commission_plan_graph/commission_plan_graph.scss",
            "sale_commission/static/src/js/commission_plan_graph/commission_plan_graph.xml",
        ],
    },
}
