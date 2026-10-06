{
    "name": "Error Incidents",
    "version": "19.0.1.0.0",
    "category": "Hidden/Tools",
    "summary": "Record the server's unexpected errors as grouped, tracked incidents",
    "description": "Captures every unexpected error raised by a request, a scheduled action or a background job, groups the occurrences by origin into incidents, masks secrets before storing them, and names the incident in the error a request returns. Expected errors raised for the user, such as access or validation errors, are not recorded.",
    "author": "AgroMarin",
    "website": "https://www.agromarin.mx",
    "license": "LGPL-3",
    "depends": [
        "mail",
    ],
    "data": [
        "security/ir.access.csv",
        "data/ir_cron.xml",
        "views/error_incident_views.xml",
        "views/error_occurrence_views.xml",
        "views/error_incident_rule_views.xml",
        "views/error_incident_menus.xml",
    ],
}
