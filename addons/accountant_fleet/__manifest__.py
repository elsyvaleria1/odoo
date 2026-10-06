{
    "name": "Vehicle Accounting Review",
    "version": "1.1",
    "oldest_upgradable_version": "1.1",
    "category": "Accounting/Accounting",
    "summary": "Expose vehicle accounting review entries in the accountant interface",
    "description": "Load the vehicle accountant menu extension and the related accounting return check template. Uses vehicle and accounting functionality supplied by its dependencies.",
    "author": "Odoo S.A.",
    "website": "https://www.odoo.com/app/accounting",
    "license": "OEEL-1",
    "depends": [
        "accountant",
        "resource_asset_vehicle",
    ],
    "data": [
        "views/accountant_fleet_menuitem.xml",
        "data/account_return_check_template.xml",
    ],
    "auto_install": True,
}
