{
    "name": "Asset Document Requirement Reports",
    "version": "19.0.1.4.0",
    "category": "Productivity/Documents",
    "summary": "Report asset document coverage, expiration and verification dates",
    "description": "Builds a SQL report over active assets, their linked documents and applicable mandatory document types. Reports missing and expiring documents, coverage percentages and document-status classifications, including assets without requirements. Requires configured document requirements and recorded dates; the report measures those records and does not certify regulatory compliance.",
    "author": "AgroMarin",
    "website": "https://agromarin.mx",
    "license": "OPL-1",
    "depends": [
        "asset_ledger_document",
        "document_compliance",
        "document_compliance_resource_asset",
        "mixin_report_sql",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_cron_data.xml",
        "reports/asset_compliance_report_views.xml",
        "views/asset_ledger_document_compliance_menus.xml",
    ],
}
