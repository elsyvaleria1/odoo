{
    "name": "Intercompany Delivery and Receipt Links",
    "version": "1.1",
    "category": "Productivity",
    "summary": "Copy completed delivery quantities into matching intercompany receipt moves",
    "description": "Adds warehouse and receipt configuration to intercompany orders and mirrors eligible completed delivery move lines into existing matching receipts when synchronization is enabled. Applies to shared products on outgoing or dropship sales deliveries; matching uses the intercompany purchase reference and product. This synchronization does not validate the receiving transfer.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "sale_stock",
        "purchase_stock",
        "sale_purchase_inter_company_rules",
    ],
    "data": [
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "auto_install": True,
}
