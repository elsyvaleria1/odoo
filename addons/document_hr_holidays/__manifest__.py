{
    "name": "Time Off Document Filing",
    "version": "1.0",
    "category": "Productivity/Documents",
    "summary": "File leave attachments using the employee company document configuration",
    "description": "Extends leave records with the Documents mixin, employee contact ownership context and employee view access. Document creation requires the company HR document setting and the base mixin creation checks.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "document_hr",
        "hr_holidays",
    ],
    "auto_install": True,
}
