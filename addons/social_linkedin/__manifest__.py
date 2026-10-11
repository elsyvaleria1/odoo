{
    "name": "LinkedIn Social Publishing",
    "version": "0.2",
    "oldest_upgradable_version": "0.2",
    "category": "Marketing/Social Marketing",
    "summary": "Publish and track content on connected LinkedIn accounts",
    "description": "Adds LinkedIn account authorization, publishing and stream synchronization to Social Publishing. Requires provider credentials and permissions for the selected accounts; available operations depend on the provider API and account access.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "social",
        "iap",
    ],
    "data": [
        "data/social_media_data.xml",
        "views/social_post_template_views.xml",
        "views/social_linkedin_preview.xml",
        "views/social_stream_posts_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "social_linkedin/static/src/js/stream_post_comment.js",
            "social_linkedin/static/src/js/stream_post_comment_list.js",
            "social_linkedin/static/src/js/stream_post_comments.js",
            "social_linkedin/static/src/js/stream_post_comments_reply.js",
            "social_linkedin/static/src/js/stream_post_kanban_record.js",
            (
                "after",
                "social/static/src/js/social_post_formatter_mixin.js",
                "social_linkedin/static/src/js/social_post_formatter_mixin.js",
            ),
            "social_linkedin/static/src/scss/social_linkedin.scss",
            "social_linkedin/static/src/xml/**/*",
        ],
        "web.assets_web_dark": [],
    },
    "auto_install": True,
}
