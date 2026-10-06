{
    "name": "Field Service Trip Deliveries",
    "version": "1.0",
    "category": "Human Resources/Planning",
    "summary": "Link customer visits to matching operator trip deliveries",
    "description": "Links outgoing deliveries by the visit user, customer hierarchy and permitted companies, including carried goods and deliveries completed on the visit day. Signing in or completing a visit refreshes links. Completion refuses unresolved linked deliveries whose trip has departed until they are marked delivered or not delivered.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "OEEL-1",
    "depends": [
        "planning_field_service",
        "stock_fleet",
    ],
    "data": [
        "security/planning_field_service_stock_fleet_security.xml",
        "views/planning_slot_views.xml",
        "views/stock_picking_views.xml",
    ],
    "assets": {
        "web.assets_tests": [
            "planning_field_service_stock_fleet/static/tests/tours/*",
        ],
    },
    "auto_install": True,
}
