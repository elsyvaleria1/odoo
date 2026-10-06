{
    "name": "Document Requirement Tracking",
    "version": "19.0.1.14.2",
    "oldest_upgradable_version": "19.0.1.14.1",
    "category": "Productivity/Documents",
    "summary": "Track configured document requirements, verification and expiration",
    "description": "Adds mandatory document-type rules, verification records, expiration activities and per-entity coverage reports over Documents. Applicable requirements and validity periods come from configuration and recorded dates. The reported status measures those configured records; it does not certify legal or regulatory compliance.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "document",
        "mixin_report_sql",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "views/document_type_views.xml",
        "views/document_document_views.xml",
        "reports/document_compliance_report_views.xml",
        "views/document_compliance_menus.xml",
    ],
    "demo": [
        "demo/document_document_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "document_compliance/static/src/components/document_details_panel/document_details_panel_patch.js",
            "document_compliance/static/src/components/document_details_panel/document_details_panel_patch.xml",
        ],
    },
}
