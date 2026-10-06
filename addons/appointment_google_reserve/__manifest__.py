{
    "name": "Reserve with Google Appointments",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Productivity",
    "summary": "Exchange appointment availability and bookings with Reserve with Google",
    "description": "Provide availability feeds and booking create/update endpoints for configured appointment types. Requires merchant and Google Reserve service configuration.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "calendar",
        "integration",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "views/appointment_type_views.xml",
        "views/google_reserve_merchant_views.xml",
        "security/ir.access.csv",
        "views/appointment_google_reserve_menus.xml",
    ],
    "demo": [
        "demo/google_reserve_demo.xml",
    ],
}
