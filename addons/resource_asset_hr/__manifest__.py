{
    "name": "Employee Asset Custody",
    "version": "1.1",
    "category": "Human Resources",
    "summary": "Select asset custodians by employee and review their assigned assets",
    "description": "Exposes asset operator, future operator and manager assignments through employee fields and adds employee asset navigation. Custody remains recorded on resource assignments. The departure wizard can end custody assignments when its release-assets option is enabled, which is the default.",
    "author": "Odoo S.A.",
    "license": "LGPL-3",
    "depends": [
        "hr",
        "resource_mail",
    ],
    "data": [
        "views/resource_asset_views.xml",
        "views/hr_views.xml",
        "wizards/wizard_hr_employee_register_departure_views.xml",
    ],
    "auto_install": True,
}
