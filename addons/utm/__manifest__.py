{
    "name": "Campaign Attribution",
    "version": "1.1",
    "category": "Marketing",
    "summary": "Track campaign, medium and source on business records",
    "description": "Provide UTM campaign, medium and source records and attribution helpers. Applications use the tracking mixin to capture campaign information.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
    ],
    "data": [
        "data/utm_medium_data.xml",
        "data/utm_source_data.xml",
        "data/utm_stage_data.xml",
        "data/utm_tag_data.xml",
        "views/utm_campaign_views.xml",
        "views/utm_medium_views.xml",
        "views/utm_source_views.xml",
        "views/utm_stage_views.xml",
        "views/utm_tag_views.xml",
        "views/utm_menus.xml",
        "security/ir.access.csv",
    ],
    "demo": [
        "demo/utm_campaign_demo.xml",
        "demo/utm_stage_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "utm/static/src/**/*",
        ],
    },
}
