{
    "name": "CRM Subscription Revenue",
    "version": "1.0",
    "category": "Sales/CRM",
    "summary": "Include subscription sales in CRM opportunity revenue tracking",
    "description": "Extend opportunity revenue updates from sales orders for subscriptions. Adjusts the related opportunity tracking behaviour.",
    "author": "Odoo S.A.",
    "license": "OEEL-1",
    "depends": [
        "crm",
        "sale_subscription",
    ],
    "data": [
        "security/ir.access.csv",
    ],
    "auto_install": True,
}
