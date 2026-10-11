{
    "name": "Maintenance Order Worksheets",
    "version": "1.2",
    "oldest_upgradable_version": "1.2",
    "category": "Supply Chain/Maintenance",
    "summary": "Open configured worksheets from maintenance orders",
    "description": "Adds worksheet-template selection and worksheet counts to maintenance orders. The worksheet action opens the existing linked worksheet or prepares a new one and requires a selected template for the maintenance-order model.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "maintenance",
        "worksheet",
    ],
    "data": [
        "security/ir.access.csv",
        "views/maintenance_views.xml",
        "views/maintenance_worksheet_views.xml",
        "reports/maintenance_custom_report.xml",
        "reports/maintenance_custom_report_templates.xml",
        "views/maintenance_worksheet_menus.xml",
    ],
    "demo": [
        "demo/maintenance_worksheet_demo.xml",
    ],
}
