{
    "name": "Field Collections and Sales",
    "version": "19.0.1.1.0",
    "category": "Accounting/Accounting",
    "summary": "Collect a cash sale on the spot, invoiced and issued at once, and optionally hold credit sales of overdue collectors",
    "description": "A collector collects a confirmed cash sale (immediate payment terms) where it happens: the order is invoiced, dated the day the customer paid and posted in one step, the invoice is issued (stamped, where a localization issues invoices), and the payment is recorded in the collector's custody with its receipt. A per-company switch, off by default, holds the sales orders on credit terms of a salesperson who keeps collections past their hand-in date.",
    "author": "AgroMarin",
    "license": "Other OSI approved licence",
    "depends": [
        "account_collection",
        "sale_stock",
    ],
    "data": [
        "security/account_collection_sale_security.xml",
        "security/ir.access.csv",
        "security/ir_access.xml",
        "views/res_config_settings_views.xml",
        "views/sale_order_views.xml",
        "wizards/wizard_sale_order_cash_collect_views.xml",
    ],
    "auto_install": True,
}
