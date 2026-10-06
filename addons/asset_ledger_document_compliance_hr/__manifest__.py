{
    "name": "Asset Document Manager Reporting",
    "version": "19.0.1.2.0",
    "category": "Productivity/Documents",
    "summary": "Group asset document requirements by the current asset manager",
    "description": "Adds the employee asset-manager dimension to the asset compliance report using the current custody assignment.",
    "author": "AgroMarin",
    "license": "OPL-1",
    "depends": [
        "asset_ledger_document_compliance",
        "asset_ledger_hr",
    ],
    "data": [
        "reports/asset_compliance_report_views.xml",
    ],
    "auto_install": True,
}
