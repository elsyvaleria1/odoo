{
    "name": "External Website Import",
    "version": "1.0.1",
    "oldest_upgradable_version": "1.0.1",
    "category": "Website/Website",
    "summary": "Request website conversion from an external service and import its returned pages",
    "description": "Submits a source URL to the configured website scraper service, polls for results and creates website pages and image attachments from the returned payload. Requires service access and an accepted request; the addon does not promise a complete or exact copy of the source website.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "website",
        "website_enterprise",
    ],
    "data": [
        "security/ir.access.csv",
        "cron/cron.xml",
        "views/website_generator_views.xml",
        "data/mail_template.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "website_generator/static/src/client_actions/*/*",
            "website_generator/static/src/systray_items/*",
        ],
        "website.website_builder_assets": [
            "website_generator/static/src/builder/**/*",
        ],
    },
}
