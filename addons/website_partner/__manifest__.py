{
    "name": "Published Contact Website Pages",
    "version": "0.1",
    "category": "Website/Website",
    "summary": "Provide website publication fields and detail pages for contacts",
    "description": "Adds website URLs, publication-related contact views and a contact detail route with its page template. Other website addons can reuse these contact pages; the module does not publish the whole address book automatically.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website",
    ],
    "data": [
        "views/res_partner_views.xml",
        "views/website_partner_templates.xml",
        "data/website_partner_data.xml",
    ],
    "demo": [
        "demo/website_partner_demo.xml",
    ],
}
