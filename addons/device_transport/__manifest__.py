{
    "name": "Device Channels and Enrollment",
    "version": "19.0.1.2.0",
    "oldest_upgradable_version": "19.0.1.2.0",
    "category": "Supply Chain/IoT",
    "summary": "Provision machine identities and independently scoped communication channels",
    "description": "Enrollments own credentials and revocation. Channels own routing and inbound policy. Hardware bindings are optional; software enrollment does not manufacture equipment. Existing device endpoints remain compatibility adapters.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "device",
    ],
    "data": [
        "security/privileges.xml",
        "security/ir.access.csv",
        "data/res_users_data.xml",
        "views/device_enrollment_views.xml",
        "views/device_channel_views.xml",
        "views/device_transport_event_views.xml",
        "views/device_transport_menus.xml",
    ],
}
