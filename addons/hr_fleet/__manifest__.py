{
    "name": "Employee Vehicles",
    "version": "2.2",
    "oldest_upgradable_version": "2.2",
    "category": "Human Resources",
    "summary": "View employee vehicle assignments and release cars on departure",
    "description": "Adds employee vehicle counts and navigation, mobility-card fields and an option to release company cars during employee departure.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "resource_asset_vehicle",
        "resource_asset_hr",
    ],
    "data": [
        "views/employee_views.xml",
        "views/fleet_vehicle_views.xml",
        "wizards/wizard_hr_employee_register_departure_views.xml",
        "data/hr_fleet_data.xml",
    ],
    "demo": [
        "demo/hr_fleet_demo.xml",
    ],
    "auto_install": True,
}
