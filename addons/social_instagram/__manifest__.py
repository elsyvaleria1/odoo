{
    "name": "Instagram Social Publishing",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Marketing/Social Marketing",
    "summary": "Publish and track content on connected Instagram Business accounts",
    "description": "Adds Instagram account authorization, publishing and stream synchronization to Social Publishing. Requires provider credentials and permissions for the selected Business accounts; available operations depend on the provider API and account access.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "social",
    ],
    "data": [
        "data/social_media_data.xml",
        "views/social_instagram_templates.xml",
        "views/social_post_template_views.xml",
        "views/social_stream_post_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "social_instagram/static/src/js/stream_post_comment.js",
            "social_instagram/static/src/js/stream_post_comment_list.js",
            "social_instagram/static/src/js/stream_post_comments.js",
            "social_instagram/static/src/js/stream_post_comments_reply.js",
            "social_instagram/static/src/js/stream_post_kanban_dashboard.js",
            "social_instagram/static/src/js/stream_post_kanban_record.js",
            (
                "after",
                "social/static/src/js/social_post_formatter_mixin.js",
                "social_instagram/static/src/js/social_post_formatter_mixin.js",
            ),
            "social_instagram/static/src/scss/social_instagram.scss",
            "social_instagram/static/src/xml/**/*",
        ],
    },
    "auto_install": True,
}
