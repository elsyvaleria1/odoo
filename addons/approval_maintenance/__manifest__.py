{
    "name": "Maintenance Approval Requests",
    "version": "19.0.1.4.0",
    "oldest_upgradable_version": "19.0.1.4.0",
    "category": "Human Resources/Approvals",
    "summary": "Create approval requests with maintenance order details",
    "description": "Extends maintenance orders with a request-creation action and a formatted reason containing equipment, products, subject, duration and vendor when present. Uses the inherited approval category and eligibility checks and links the created request back to its order. Approval execution and maintenance workflows come from the dependencies.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "approval_stock",
        "asset_ledger_maintenance",
    ],
    "data": [
        "data/approval_category_data.xml",
    ],
}
