{
    "name": "Website Editor and Setup Extensions",
    "category": "Website/Website",
    "summary": "Extend website navigation, editor controls and optional feature setup",
    "description": "Adds website editor navigation and appearance controls, configurator entries for appointment and helpdesk addons, and appointment snippet installation entries. An enabled website-generator setting exposes an import setup action that creates a website and installs the generator if needed; imported-site conversion belongs to that addon.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "website",
    ],
    "data": [
        "data/website_data.xml",
        "views/snippets/snippets.xml",
        "views/website_enterprise_templates.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "website_enterprise/static/src/client_actions/*/*",
        ],
        "website.assets_editor": [
            "website_enterprise/static/src/js/systray_items/*.js",
            "website_enterprise/static/src/services/color_scheme_service_patch.js",
            "website_enterprise/static/src/components/navbar/*",
            "website_enterprise/static/src/systray_items/*",
        ],
    },
    "auto_install": True,
}
