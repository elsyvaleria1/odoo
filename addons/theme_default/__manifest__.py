{
    "name": "Default Website Theme",
    "version": "1.0",
    "category": "Theme",
    "sequence": 1000,
    "summary": "Provide the default theme choice for website creation",
    "description": "Register the default website theme. Its visual components are supplied by the Website dependency.",
    "author": "Odoo S.A.",
    "images": [
        "static/description/cover.png",
        "static/description/theme_default_screenshot.jpg",
    ],
    "license": "LGPL-3",
    "depends": [
        "website",
    ],
    "data": [
        "data/generate_primary_template.xml",
    ],
}
