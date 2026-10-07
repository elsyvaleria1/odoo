{
    "name": "Asset Operator Assignments",
    "version": "19.0.1.11.0",
    "oldest_upgradable_version": "19.0.1.9.0",
    "category": "Human Resources/Fleet",
    "summary": "Track employee custody and operator changes for serialized assets",
    "description": "Records operator and asset-manager assignments in asset logs. Provides scheduled operator changes and dated employee assignment history for assets backed by stock lots.",
    "author": "AgroMarin",
    "website": "https://agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "asset_ledger",
        "resource_asset_hr",
    ],
    "data": [
        "security/ir.access.csv",
        "views/product_asset_log_views.xml",
        "views/resource_asset_views.xml",
    ],
    "demo": [
        "demo/hr_employee_demo.xml",
        "demo/product_trace_assignment_demo.xml",
    ],
}
