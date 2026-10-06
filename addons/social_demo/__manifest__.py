{
    "name": "Social Demonstration Data and Simulations",
    "version": "1.0",
    "category": "Marketing/Social Marketing",
    "summary": "Load social demo records and simulate selected posting and interaction flows",
    "description": "Provides demo accounts and streams for the bundled social providers, with overrides for posting, statistics, comments and selected upload interactions. Intended for demonstrations with demo data loaded; the implemented simulations do not establish complete isolation of every provider operation.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "social",
        "social_facebook",
        "social_twitter",
        "social_linkedin",
        "social_youtube",
        "social_instagram",
        "product",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "demo": [
        "demo/social_demo.xml",
        "demo/social_demo_facebook.xml",
        "demo/social_demo_linkedin.xml",
        "demo/social_demo_instagram.xml",
        "demo/social_demo_twitter.xml",
        "demo/social_demo_youtube.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "social_demo/static/src/js/social_youtube_upload_field.js",
            "social_demo/static/src/js/stream_post_comment.js",
            "social_demo/static/src/js/stream_post_comments_reply.js",
        ],
    },
}
