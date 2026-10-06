{
    "name": "Appointment-Generated Task Dates",
    "version": "1.1",
    "category": "Services/Appointment",
    "summary": "Link sales-generated tasks to their appointment and copy its dates",
    "description": "Extends task generation from appointment-linked sales lines with the calendar event reference and appointment dates. Adds task navigation to the appointment; requires a sales product configured to generate project work.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "website_appointment_sale",
        "sale_project",
    ],
    "data": [
        "views/project_views.xml",
    ],
    "auto_install": True,
}
