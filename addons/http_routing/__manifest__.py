{
    "name": "Frontend URL Routing",
    "category": "Hidden",
    "sequence": 9100,
    "summary": "Resolve localized frontend URLs and record slugs",
    "description": "Adds language-prefix handling, slug converters, frontend translation loading and error-page rendering to HTTP routes.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "web",
        "html_editor",
    ],
    "data": [
        "views/http_routing_template.xml",
        "views/res_lang_views.xml",
    ],
    "post_init_hook": "_post_init_hook",
}
