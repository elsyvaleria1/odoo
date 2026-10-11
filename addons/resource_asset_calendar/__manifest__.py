{
    "name": "Asset Appointment Availability",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Restrict appointment bookings by asset availability",
    "description": "Links assets to appointment types and checks their bookable state when preparing slots and validating booking lines.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "resource_mail",
        "calendar",
    ],
    "data": [
        "views/resource_asset_views.xml",
    ],
    "auto_install": True,
}
