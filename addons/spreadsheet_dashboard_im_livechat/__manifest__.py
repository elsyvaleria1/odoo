{
    "name": "Live Chat Spreadsheet Dashboards",
    "version": "1.0",
    "category": "Productivity/Dashboard",
    "summary": "Add Live Chat, Live Chat - Ongoing Sessions spreadsheet dashboards",
    "description": "Install preconfigured spreadsheet dashboards for Live Chat, Live Chat - Ongoing Sessions. The supplied spreadsheet layouts define their business data sources and calculations.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "spreadsheet_dashboard",
        "im_livechat",
    ],
    "data": [
        "data/livechat_ongoing_sessions_actions.xml",
        "views/spreadsheet_dashboard_im_livechat_menus.xml",
        "data/dashboards.xml",
    ],
    "auto_install": [
        "im_livechat",
    ],
}
