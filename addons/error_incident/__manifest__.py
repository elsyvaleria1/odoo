{
    "name": "Error Incidents",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "summary": "Record the server's and the browser's unexpected errors as grouped, tracked incidents",
    "description": "Captures every unexpected error raised by a request, a scheduled action, a background job or the browser, locates browser errors in the sources through the bundles' source maps, groups the occurrences by origin into incidents, masks secrets before storing them, names the incident in the error a request returns, and shows the user who hit it where it stands, live, in the error dialog, with a notice once it is fixed. Expected errors raised for the user, such as access or validation errors, are not recorded.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "mail",
    ],
    "data": [
        "security/res_groups.xml",
        "security/ir.access.csv",
        "data/ir_cron.xml",
        "views/error_incident_views.xml",
        "views/error_occurrence_views.xml",
        "views/error_incident_rule_views.xml",
        "views/error_incident_menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "error_incident/static/src/**/*",
        ],
        "web.assets_unit_tests": [
            "error_incident/static/tests/**/*",
        ],
    },
}
