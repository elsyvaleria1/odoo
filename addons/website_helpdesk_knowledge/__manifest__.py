{
    "name": "Help Center Knowledge Articles",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Include Knowledge articles in website help centers",
    "description": "Adds team article selection, recent-article displays and article search results to help-center pages. Public visibility follows the article publishing and access settings.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "website_helpdesk",
        "knowledge",
    ],
    "data": [
        "views/helpdesk_templates.xml",
        "views/helpdesk_views.xml",
        "data/knowledge_data.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "website_helpdesk_knowledge/static/tests/tours/**/*",
        ],
    },
    "auto_install": True,
}
