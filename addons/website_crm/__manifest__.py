{
    "name": "Website CRM Forms",
    "version": "2.1",
    "category": "Website/Website",
    "sequence": 54,
    "summary": "Create CRM leads or opportunities from configured website forms",
    "description": "Extends website form handling with CRM lead creation, website team and salesperson defaults, and visitor links. Includes contact-input processing for submitted leads. Forms must be configured to target CRM records; installing the addon does not convert every website form into a lead form.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website",
        "crm",
    ],
    "data": [
        "security/ir.access.csv",
        "data/crm_lead_merge_template.xml",
        "data/ir_actions_data.xml",
        "data/ir_model_data.xml",
        "views/crm_lead_views.xml",
        "views/website_visitor_views.xml",
        "views/website_templates_contactus.xml",
    ],
    "assets": {
        "website.website_builder_assets": [
            "website_crm/static/src/js/website_crm_editor.js",
        ],
        "web.assets_tests": [
            "website_crm/static/tests/**/*",
        ],
    },
    "auto_install": True,
}
