{
    "name": "Intercompany Sales and Purchase Orders",
    "version": "1.1",
    "category": "Productivity",
    "summary": "Generate counterpart sales or purchase orders on intercompany confirmation",
    "description": "Creates a purchase order from a confirmed sales order, or a sales order from a confirmed purchase order, when the receiving company enables that direction. Requires an intercompany user and suitable shared configuration; generated orders can be automatically confirmed by the document-state setting. Invoice generation belongs to the accounting dependency.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale",
        "sale_team",
        "purchase",
        "account_inter_company_rules",
    ],
    "data": [
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "auto_install": True,
}
