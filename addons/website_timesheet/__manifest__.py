{
    "name": "Website Portal Timesheet Visibility",
    "version": "1.0",
    "category": "Website/Website",
    "summary": "Respect the website-specific portal timesheet view when checking visibility",
    "description": "Overrides the portal timesheet visibility helper to read the active state of the most specific matching website view. It changes the visibility decision used by consumers of that helper, not record access rights.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "website",
        "hr_timesheet",
    ],
    "auto_install": True,
}
