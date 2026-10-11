{
    "name": "Document Sharing Website Domains",
    "version": "1.0",
    "category": "Productivity/Documents",
    "sequence": 8010,
    "summary": "Choose a website domain for document and folder access links",
    "description": "Adds website selection and access-URL computation to shared documents and folders, with website consistency checks. Selecting a website changes link routing; document sharing permissions remain governed by Documents.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/documents",
    "license": "Other OSI approved licence",
    "depends": [
        "document",
        "website",
    ],
    "data": [
        "views/document_document_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "website_document/static/src/views/**/*",
        ],
    },
    "auto_install": True,
}
