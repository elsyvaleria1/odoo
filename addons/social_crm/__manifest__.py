{
    "name": "Social Post Lead Attribution",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Marketing/Social Marketing",
    "summary": "Create leads from social posts or comments and count leads by post source",
    "description": "Adds a lead-creation wizard for social stream posts and comments, customer matching and UTM defaults. Social post statistics count leads sharing the recorded source; they do not establish that the post caused a sale.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "social",
        "crm",
    ],
    "data": [
        "security/ir.access.csv",
        "data/social_crm_data.xml",
        "data/social_post_to_lead_templates.xml",
        "views/social_post_views.xml",
        "wizards/wizard_social_stream_post_create_lead_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            (
                "after",
                "social/static/src/js/stream_post_comment.js",
                "social_crm/static/src/js/stream_post_comment.js",
            ),
            (
                "after",
                "social/static/src/js/stream_post_comments.js",
                "social_crm/static/src/js/stream_post_comments.js",
            ),
            "social_crm/static/src/xml/**/*",
        ],
    },
    "auto_install": True,
}
