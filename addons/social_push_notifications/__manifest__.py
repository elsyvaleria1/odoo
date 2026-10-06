{
    "name": "Website Push Notifications",
    "version": "1.1",
    "category": "Marketing/Social Marketing",
    "summary": "Send push messages to subscribed website visitors",
    "description": "Stores visitor push subscriptions and adds push posts to social campaigns. Requires configured Firebase messaging credentials and browser permission from each recipient.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "social",
        "website",
    ],
    "external_dependencies": {
        "python": [
            "google-auth",
        ],
        "apt": {
            "google-auth": "python3-google-auth",
        },
    },
    "data": [
        "security/ir.access.csv",
        "views/social_post_template_views.xml",
        "views/social_post_views.xml",
        "views/res_config_settings_views.xml",
        "views/social_push_notifications_templates.xml",
        "views/website_visitor_views.xml",
        "views/utm_campaign_views.xml",
        "data/social_media_data.xml",
        "views/social_push_notifications_menus.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "social_push_notifications/static/src/interactions/push_notification_widget.js",
            "social_push_notifications/static/src/scss/social_push_notifications_frontend.scss",
            "social_push_notifications/static/src/xml/social_push_notifications_templates.xml",
        ],
        "web.assets_backend": [
            "social_push_notifications/static/src/scss/social_push_notifications.scss",
        ],
    },
    "auto_install": True,
    "post_init_hook": "_create_social_accounts",
}
