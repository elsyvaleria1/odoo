{
    "name": "AvaTax Sales Taxes",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Calculate sales order taxes through AvaTax",
    "description": "Prepare AvaTax service parameters from sales orders and preserve the relevant grouping values when creating invoices. Requires configured AvaTax fiscal positions and credentials.",
    "author": "Odoo S.A.",
    "license": "Other OSI approved licence",
    "depends": [
        "sale_external_tax",
        "account_avatax",
        "sale",
    ],
    "data": [
        "views/sale_order_views.xml",
        "views/sale_portal_templates.xml",
        "reports/sale_order.xml",
    ],
    "auto_install": True,
}
